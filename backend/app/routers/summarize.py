"""Summarize API (Part C): validate -> quota -> cache -> enqueue, then poll.

  POST /api/summarize   create/return a job (idempotent), 202 + job_id
  GET  /api/jobs/{id}   poll status; returns summaries when done
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..llm import LIGHT_TYPES
from ..models import DailyUsage, Job, JobStatus, Summary, User
from ..quota import check_and_reserve
from ..security import utcnow
from ..transcript import (
    NoTranscript,
    TranscriptError,
    extract_video_id,
    fetch_captions,
    fetch_metadata,
)

router = APIRouter(prefix="/api", tags=["summarize"])

VALID_TYPES = set(LIGHT_TYPES)
VALID_SOURCES = {"paste", "api", "extension", "audio"}


class SummarizeIn(BaseModel):
    transcript_text: str = ""  # omitted for audio jobs (the worker transcribes)
    summary_types: list[str] = Field(default_factory=lambda: list(LIGHT_TYPES))
    complete_notes: bool = False
    video_id: str | None = None
    source: str = "paste"
    # Regenerate: bust the content-bound cache for the requested types and run a
    # fresh (quota-counted) job instead of serving the previous result.
    force: bool = False


class SummarizeOut(BaseModel):
    job_id: str
    status: str


class TranscriptIn(BaseModel):
    url: str


class TranscriptOut(BaseModel):
    video_id: str
    title: str | None = None
    duration: int | None = None  # seconds (from YouTube Data API v3 if configured)
    transcript: str
    truncated: bool
    # No captions found, but audio transcription is available: the client should
    # submit an audio job (source="audio") and the worker will transcribe it.
    needs_audio: bool = False


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
    if not types and not body.complete_notes:
        raise HTTPException(422, "Pick at least one summary type.")
    video_id = (body.video_id or "").strip()[:16] or None
    wanted = types + (["notes"] if body.complete_notes else [])

    # Audio job: no captions were available, so the worker will download + transcribe
    # the audio (slow). The transcript/hash are unknown until then, so we defer the
    # cache check to the worker and key idempotency on the video id instead.
    is_audio = body.source == "audio" and bool(video_id)
    if is_audio:
        transcript = ""
        tsha = ""
        idem_basis = f"audio:{video_id}"
    else:
        transcript = _validate_transcript(body.transcript_text)
        tsha = _sha256(transcript)
        idem_basis = tsha

    # Regenerate (force) is always a brand-new job: salt the idempotency key so
    # it doesn't short-circuit to a prior job. The worker (not this request)
    # regenerates and OVERWRITES the cached rows on success, so we never delete
    # another user's completed result here.
    # Idempotency key (Part C): same user + content + options -> same job.
    salt = f"|force|{uuid4().hex}" if body.force else ""
    idem = _sha256(f"{user.id}|{idem_basis}|{','.join(types)}|{int(body.complete_notes)}{salt}")
    existing = (
        await session.execute(select(Job).where(Job.idempotency_key == idem))
    ).scalar_one_or_none()
    if existing is not None:
        # A prior attempt that errored out should RE-RUN on retry (e.g. after a
        # fix or a transient failure) — otherwise the idempotent lookup keeps
        # handing back the stale failure forever. Re-queue it (reset attempts so
        # the worker will claim it again) instead of returning the error.
        if existing.status == JobStatus.error.value:
            existing.status = JobStatus.queued.value
            existing.phase = "queued"
            existing.error = None
            existing.attempts = 0
            existing.lease_owner = None
            existing.lease_expires_at = None
            await session.commit()
        return SummarizeOut(job_id=existing.id, status=existing.status)

    # Content-bound cache (G4): is every requested type already generated? An
    # audio job's transcript isn't known yet, so the worker checks the cache after
    # transcribing — here it always runs.
    if is_audio:
        all_cached = False
    else:
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
        # A forced regenerate must always run (and re-bill quota), even if cached.
        all_cached = (not body.force) and all(t in cached for t in wanted)

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
        force=body.force,
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


@router.post("/transcript", response_model=TranscriptOut)
async def get_transcript(body: TranscriptIn, user: User = Depends(get_current_user)):
    """Resolve a YouTube transcript by URL (M3) — CAPTIONS ONLY, so the request
    stays fast. If the video has no captions but audio transcription is available,
    return needs_audio=True; the client then submits an audio job and the worker
    transcribes the audio in the background."""
    video_id = extract_video_id(body.url)
    if not video_id:
        raise HTTPException(422, "Enter a valid YouTube video URL.")
    try:
        text = await fetch_captions(video_id)
    except NoTranscript:
        audio_ok = settings.audio_fallback_enabled and bool(settings.groq_api_key or settings.gemini_keys)
        if not audio_ok:
            raise HTTPException(422, "This video has no captions available.")
        title, duration = await fetch_metadata(video_id)
        return TranscriptOut(
            video_id=video_id, title=title, duration=duration,
            transcript="", truncated=False, needs_audio=True,
        )
    except TranscriptError as exc:
        raise HTTPException(exc.status, exc.detail)
    truncated = len(text) > settings.transcript_max_chars
    if truncated:
        text = text[: settings.transcript_max_chars].rstrip()
    title, duration = await fetch_metadata(video_id)
    return TranscriptOut(video_id=video_id, title=title, duration=duration, transcript=text, truncated=truncated)


@router.get("/usage")
async def usage(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Today's per-user job usage against the daily cap (UTC day)."""
    day = utcnow().strftime("%Y-%m-%d")
    used = (
        await session.execute(
            select(DailyUsage.jobs_count).where(
                DailyUsage.scope == f"user:{user.id}", DailyUsage.day == day
            )
        )
    ).scalar_one_or_none() or 0
    limit = settings.per_user_daily_jobs
    tomorrow = (utcnow() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "jobs_used": used,
        "jobs_limit": limit,
        "jobs_remaining": max(0, limit - used),
        "day": day,
        "resets_at": tomorrow.isoformat() + "Z",
    }


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
        # Expose the resolved transcript (e.g. from audio ASR) so the client can
        # regenerate a type without re-transcribing.
        out["transcript"] = job.transcript
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


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete one of the caller's jobs. Shared, content-bound Summary rows are
    left intact (they're a cross-user cache keyed by transcript hash, not owned
    by this job), so deleting a job only removes it from the user's history."""
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user.id:  # ownership check (no IDOR)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await session.delete(job)
    await session.commit()
    return {"ok": True}
