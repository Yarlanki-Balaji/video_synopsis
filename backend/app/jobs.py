"""In-process job worker + reaper (E2-E4).

Postgres is the source of truth. One worker claims a job at a time (Semaphore(1))
by atomically setting a lease with a fencing token (lease_count); every later
write is gated on that token. A heartbeat keeps the lease alive during LLM calls,
results are persisted incrementally (so a later failure never discards paid work),
and a periodic reaper recovers/fails orphaned jobs.

Note: this assumes a single web process owns the worker. Running multiple uvicorn
processes is safe for correctness (the fence prevents clobbering) but each would
run its own worker; for prod, run one worker or use an external queue (E4 "Later").
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from .config import settings
from .db import SessionLocal
from .llm import RateLimited, RequestTooLarge, summarize_long as llm_summarize
from .models import Job, JobStatus, Summary
from .quota import open_breaker, record_tokens
from .security import utcnow

logger = logging.getLogger("app.jobs")

WORKER_ID = uuid4().hex[:12]
_sem = asyncio.Semaphore(1)
_stop = asyncio.Event()
_worker_task: asyncio.Task | None = None
_reaper_task: asyncio.Task | None = None


async def _claim_one() -> tuple[str, int] | None:
    """Atomically claim a queued or lease-expired job (with attempts left)."""
    async with SessionLocal() as session:
        now = utcnow()
        runnable = (Job.status == JobStatus.queued.value) | (
            (Job.status == JobStatus.running.value) & (Job.lease_expires_at < now)
        )
        candidate = (
            await session.execute(
                select(Job.id, Job.lease_count)
                .where(Job.attempts < settings.job_max_attempts, runnable)
                .order_by(Job.created_at)
                .limit(1)
            )
        ).first()
        if candidate is None:
            return None
        job_id, lease_count = candidate
        fence = lease_count + 1
        res = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_count == lease_count, runnable)
            .values(
                status=JobStatus.running.value,
                lease_owner=WORKER_ID,
                lease_expires_at=now + timedelta(seconds=settings.job_lease_seconds),
                lease_count=fence,
                attempts=Job.attempts + 1,
                phase="claimed",
            )
        )
        if res.rowcount != 1:
            await session.rollback()
            return None
        await session.commit()
        return job_id, fence


async def _renew_lease(job_id: str, fence: int) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_count == fence, Job.lease_owner == WORKER_ID)
            .values(lease_expires_at=utcnow() + timedelta(seconds=settings.job_lease_seconds))
        )
        await session.commit()


async def _set_phase(job_id: str, fence: int, phase: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_count == fence, Job.lease_owner == WORKER_ID)
            .values(phase=phase, lease_expires_at=utcnow() + timedelta(seconds=settings.job_lease_seconds))
        )
        await session.commit()


class _Heartbeat:
    """Keep the lease alive while a (possibly slow) LLM call runs (C#1)."""

    def __init__(self, job_id: str, fence: int):
        self._job_id, self._fence, self._task = job_id, fence, None

    async def _loop(self) -> None:
        interval = max(5, settings.job_lease_seconds // 3)
        try:
            while True:
                await asyncio.sleep(interval)
                await _renew_lease(self._job_id, self._fence)
        except asyncio.CancelledError:
            pass

    async def __aenter__(self) -> "_Heartbeat":
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


async def _persist(job_id: str, fence: int, results: dict[str, str], tokens: int, *, tsha, lang, source, video_id, force: bool = False) -> bool:
    """Persist generated summaries + token usage, gated on the fence. Single
    worker means no concurrent writers, so insert-if-missing is enough — except
    a forced regenerate OVERWRITES the existing row in place (so the old content
    stays readable until the new content commits; a failed regen never leaves a
    hole, and another user's completed job is never emptied)."""
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.lease_count != fence:
            return False  # we were re-leased — abandon (results are stale)
        existing = {
            r.type: r
            for r in (
                await session.execute(
                    select(Summary).where(
                        Summary.transcript_sha256 == tsha, Summary.lang == lang
                    )
                )
            ).scalars().all()
        }
        for type_, content in results.items():
            row = existing.get(type_)
            if row is not None:
                if force:  # regenerate: replace the cached content in place
                    row.content = content
                    row.source = source
                continue
            session.add(
                Summary(transcript_sha256=tsha, video_id=video_id, type=type_, lang=lang, content=content, source=source)
            )
        if tokens:
            await record_tokens(session, tokens)
        await session.commit()
        return True


async def _fail(job_id: str, fence: int, message: str, *, breaker: bool = False, permanent: bool = False) -> None:
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.lease_count != fence:
            return
        if permanent or job.attempts >= settings.job_max_attempts:
            values = dict(status=JobStatus.error.value, phase="error")
        else:
            values = dict(status=JobStatus.queued.value, phase="requeued")
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_count == fence)
            .values(error=message, lease_owner=None, lease_expires_at=None, **values)
        )
        if breaker:
            await open_breaker(session, message)
        await session.commit()


async def _run_job(job_id: str, fence: int) -> None:
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None or job.lease_count != fence or job.lease_owner != WORKER_ID:
            return
        transcript, tsha, lang, source, video_id = (
            job.transcript, job.transcript_sha256, job.lang, job.source, job.video_id
        )
        force = job.force
        light_types = [t for t in job.summary_types.split(",") if t]
        want_notes = job.complete_notes
        existing = set(
            (
                await session.execute(
                    select(Summary.type).where(Summary.transcript_sha256 == tsha, Summary.lang == lang)
                )
            ).scalars().all()
        )

    # A forced regenerate re-runs every requested type even if cached.
    missing_light = light_types if force else [t for t in light_types if t not in existing]
    need_notes = want_notes if force else (want_notes and "notes" not in existing)
    common = dict(tsha=tsha, lang=lang, source=source, video_id=video_id, force=force)

    try:
        if missing_light:
            await _set_phase(job_id, fence, "summarizing")
            async with _Heartbeat(job_id, fence):
                r = await llm_summarize(transcript, missing_light)
            # Persist immediately so a later notes failure can't discard this.
            if not await _persist(job_id, fence, r.content, r.tokens_used, **common):
                return
        if need_notes:
            await _set_phase(job_id, fence, "notes")
            async with _Heartbeat(job_id, fence):
                r = await llm_summarize(transcript, ["notes"])
            if not await _persist(job_id, fence, {"notes": r.content["notes"]}, r.tokens_used, **common):
                return
    except RequestTooLarge:
        await _fail(
            job_id, fence,
            "Transcript is too large for the model's per-request limit. Try a shorter transcript.",
            permanent=True,
        )
        return
    except RateLimited as exc:
        await _fail(job_id, fence, str(exc), breaker=True)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s failed during summarization", job_id)
        await _fail(job_id, fence, str(exc)[:200], breaker=False)
        return

    async with SessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.lease_count == fence, Job.lease_owner == WORKER_ID)
            .values(status=JobStatus.done.value, phase="done", error=None, lease_owner=None, lease_expires_at=None)
        )
        await session.commit()


async def reap_orphans() -> None:
    """Recover jobs left 'running' by a dead runner; fail those out of attempts (E4).
    Bumps lease_count so the previous runner is fenced off."""
    async with SessionLocal() as session:
        now = utcnow()
        stuck = (Job.status == JobStatus.running.value) & (
            (Job.lease_expires_at < now) | (Job.lease_expires_at.is_(None))
        )
        await session.execute(
            update(Job)
            .where(stuck, Job.attempts >= settings.job_max_attempts)
            .values(status=JobStatus.error.value, phase="error", error="exceeded max attempts",
                    lease_owner=None, lease_expires_at=None, lease_count=Job.lease_count + 1)
        )
        await session.execute(
            update(Job)
            .where(stuck, Job.attempts < settings.job_max_attempts)
            .values(status=JobStatus.queued.value, phase="recovered",
                    lease_owner=None, lease_expires_at=None, lease_count=Job.lease_count + 1)
        )
        await session.commit()


async def _worker_loop() -> None:
    logger.info("job worker %s started", WORKER_ID)
    while not _stop.is_set():
        try:
            claim = await _claim_one()
            if claim is None:
                await asyncio.sleep(settings.worker_poll_seconds)
                continue
            async with _sem:
                await _run_job(*claim)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("worker loop error")
            await asyncio.sleep(settings.worker_poll_seconds)
    logger.info("job worker %s stopped", WORKER_ID)


async def _reaper_loop() -> None:
    while not _stop.is_set():
        try:
            await reap_orphans()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("reaper error")
        for _ in range(settings.reaper_interval_seconds):
            if _stop.is_set():
                break
            await asyncio.sleep(1)


async def start_worker() -> None:
    global _worker_task, _reaper_task
    await reap_orphans()
    _stop.clear()
    _worker_task = asyncio.create_task(_worker_loop())
    _reaper_task = asyncio.create_task(_reaper_loop())


async def stop_worker() -> None:
    _stop.set()
    for task in (_worker_task, _reaper_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
