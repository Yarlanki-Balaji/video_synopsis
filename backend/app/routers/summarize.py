"""Summarize API (Part C): validate -> quota -> cache -> enqueue, then poll.

  POST /api/summarize   create/return a job (idempotent), 202 + job_id
  GET  /api/jobs/{id}   poll status; returns summaries when done
"""
from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..llm import LIGHT_TYPES
from ..models import Job, JobStatus, Summary, User
from ..quota import check_and_reserve

router = APIRouter(prefix="/api", tags=["summarize"])

VALID_TYPES = set(LIGHT_TYPES)
VALID_SOURCES = {"paste", "api", "extension"}


class SummarizeIn(BaseModel):
    transcript_text: str
    summary_types: list[str] = Field(default_factory=lambda: list(LIGHT_TYPES))
    complete_notes: bool = False
    video_id: str | None = None
    source: str = "paste"


class SummarizeOut(BaseModel):
    job_id: str
    status: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_transcript(text: str) -> str:
    """Basic empty/invalid floors (D5)."""
    t = text.strip()
    if len(t) < settings.transcript_min_chars:
        raise HTTPException(422, "Transcript is too short.")
    if len(t) > settings.transcript_max_chars:
        raise HTTPException(422, f"Transcript exceeds {settings.transcript_max_chars} characters.")
    if not re.search(r"[A-Za-z]{2,}", t):
        raise HTTPException(422, "That doesn't look like a transcript.")
    words = t.split()
    if len(set(words)) < 5:
        raise HTTPException(422, "Transcript looks empty or repetitive.")
    # Reject low-diversity spam (e.g. one phrase repeated thousands of times).
    if len(words) > 30 and len(set(words)) / len(words) < 0.15:
        raise HTTPException(422, "Transcript looks too repetitive.")
    return t


@router.post("/summarize", response_model=SummarizeOut, status_code=status.HTTP_202_ACCEPTED)
async def summarize(
    body: SummarizeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    types = sorted({t for t in body.summary_types if t in VALID_TYPES})
    if not types:
        raise HTTPException(422, "Pick at least one summary type.")
    transcript = _validate_transcript(body.transcript_text)
    tsha = _sha256(transcript)
    video_id = (body.video_id or "").strip()[:16] or None

    # Idempotency key (Part C): same user + content + options -> same job.
    idem = _sha256(f"{user.id}|{tsha}|{','.join(types)}|{int(body.complete_notes)}")
    existing = (
        await session.execute(select(Job).where(Job.idempotency_key == idem))
    ).scalar_one_or_none()
    if existing is not None:
        return SummarizeOut(job_id=existing.id, status=existing.status)

    # Content-bound cache (G4): is every requested type already generated?
    wanted = types + (["notes"] if body.complete_notes else [])
    cached = set(
        (
            await session.execute(
                select(Summary.type).where(
                    Summary.transcript_sha256 == tsha,
                    Summary.lang == "en",
                    Summary.type.in_(wanted),
                )
            )
        ).scalars().all()
    )
    all_cached = all(t in cached for t in wanted)

    # Quota + breaker only when real work is needed (cache hits are free).
    if not all_cached:
        decision = await check_and_reserve(session, user.id)
        if not decision.allowed:
            await session.rollback()
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, decision.reason or "Daily limit reached.")

    job = Job(
        user_id=user.id,
        idempotency_key=idem,
        source=body.source if body.source in VALID_SOURCES else "paste",
        video_id=video_id,
        transcript_sha256=tsha,
        transcript=transcript,
        lang="en",
        summary_types=",".join(types),
        complete_notes=body.complete_notes,
        status=JobStatus.done.value if all_cached else JobStatus.queued.value,
        phase="cached" if all_cached else "queued",
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        # Idempotency race: another request created the same job first.
        await session.rollback()
        existing = (
            await session.execute(select(Job).where(Job.idempotency_key == idem))
        ).scalar_one_or_none()
        if existing is not None:
            return SummarizeOut(job_id=existing.id, status=existing.status)
        raise
    return SummarizeOut(job_id=job.id, status=job.status)


@router.get("/jobs")
async def list_jobs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(50)
        )
    ).scalars().all()
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "created_at": j.created_at.isoformat(),
            "summary_types": [t for t in j.summary_types.split(",") if t],
            "complete_notes": j.complete_notes,
            "preview": (j.transcript[:80] + "…") if len(j.transcript) > 80 else j.transcript,
        }
        for j in rows
    ]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user.id:  # ownership check (no IDOR)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    out: dict = {
        "job_id": job.id,
        "status": job.status,
        "phase": job.phase,
        "error": job.error,
        "summary_types": [t for t in job.summary_types.split(",") if t],
        "complete_notes": job.complete_notes,
        "summaries": {},
    }
    if job.status == JobStatus.done.value:
        wanted = out["summary_types"] + (["notes"] if job.complete_notes else [])
        rows = (
            await session.execute(
                select(Summary).where(
                    Summary.transcript_sha256 == job.transcript_sha256,
                    Summary.lang == job.lang,
                    Summary.type.in_(wanted),
                )
            )
        ).scalars().all()
        out["summaries"] = {r.type: r.content for r in rows}
    return out
