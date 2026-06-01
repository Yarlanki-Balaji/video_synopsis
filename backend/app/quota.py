"""Postgres-authoritative quotas + circuit breaker (F5).

Control state lives in Postgres (never the evictable cache) and **fails closed**.
Counter updates are atomic conditional UPDATEs (`... WHERE count < cap`) so the
caps actually hold under concurrency (no read-modify-write lost updates).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import DailyUsage, ServiceState
from .security import utcnow

logger = logging.getLogger("app.quota")


def _today() -> str:
    return utcnow().strftime("%Y-%m-%d")


@dataclass
class QuotaDecision:
    allowed: bool
    reason: str | None = None


async def _ensure_row(session: AsyncSession, scope: str, day: str) -> None:
    """Get-or-create the counter row, tolerating a concurrent creator."""
    exists = (
        await session.execute(
            select(DailyUsage.id).where(DailyUsage.scope == scope, DailyUsage.day == day)
        )
    ).scalar_one_or_none()
    if exists is not None:
        return
    try:
        async with session.begin_nested():
            session.add(DailyUsage(scope=scope, day=day, jobs_count=0, tokens_used=0))
    except IntegrityError:
        pass  # another request created it first — fine


async def _try_increment_jobs(session: AsyncSession, scope: str, day: str, cap: int) -> bool:
    """Atomic: increment only if still under cap. Returns True if reserved."""
    res = await session.execute(
        update(DailyUsage)
        .where(DailyUsage.scope == scope, DailyUsage.day == day, DailyUsage.jobs_count < cap)
        .values(jobs_count=DailyUsage.jobs_count + 1)
    )
    return res.rowcount == 1


async def check_and_reserve(session: AsyncSession, user_id: str) -> QuotaDecision:
    """Check breaker + caps and, if allowed, reserve one job slot.

    Increments run in the caller's transaction; on denial the caller rolls back,
    so any partial reservation (e.g. user ok but global over cap) is undone.
    """
    try:
        day = _today()
        state = await session.get(ServiceState, 1)
        if state and state.breaker_open_until and state.breaker_open_until > utcnow():
            return QuotaDecision(False, "Service is paused (at capacity). Please try again later.")

        await _ensure_row(session, f"user:{user_id}", day)
        await _ensure_row(session, "global", day)

        glob_tokens = (
            await session.execute(
                select(DailyUsage.tokens_used).where(
                    DailyUsage.scope == "global", DailyUsage.day == day
                )
            )
        ).scalar_one()
        if glob_tokens >= settings.global_daily_tokens:
            return QuotaDecision(False, "We're at daily capacity. Back tomorrow.")

        if not await _try_increment_jobs(session, f"user:{user_id}", day, settings.per_user_daily_jobs):
            return QuotaDecision(False, "Daily limit reached for your account. Back tomorrow.")
        if not await _try_increment_jobs(session, "global", day, settings.global_daily_jobs):
            return QuotaDecision(False, "We're at daily capacity. Back tomorrow.")
        return QuotaDecision(True)
    except Exception:
        # Fail closed (F5 / R7) — but log so an outage isn't silent.
        logger.exception("quota check failed; failing closed")
        return QuotaDecision(False, "Service temporarily unavailable.")


async def record_tokens(session: AsyncSession, tokens: int) -> None:
    if tokens <= 0:
        return
    day = _today()
    await _ensure_row(session, "global", day)
    await session.execute(
        update(DailyUsage)
        .where(DailyUsage.scope == "global", DailyUsage.day == day)
        .values(tokens_used=DailyUsage.tokens_used + tokens)
    )


async def open_breaker(session: AsyncSession, reason: str) -> None:
    state = await session.get(ServiceState, 1)
    if state is None:
        state = ServiceState(id=1)
        session.add(state)
    state.breaker_open_until = utcnow() + timedelta(minutes=settings.breaker_cooldown_minutes)
    state.reason = reason[:255]
