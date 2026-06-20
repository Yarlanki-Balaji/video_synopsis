"""Per-user comprehension features powered by the Hermes agent sidecar (NEW).

  GET  /api/comprehension/profile  -> the caller's current comprehension profile
  POST /api/comprehension/summary  -> adaptive synopsis tailored to that profile
  POST /api/comprehension/quiz     -> N topic questions + 2 feedback questions
  POST /api/comprehension/assess   -> grade answers, UPDATE the caller's profile

Per-user adaptation lives in our DB (models.ComprehensionProfile). The assess step
returns an updated profile which we persist; the next summary uses it. Auth is the
same JWT dependency as the rest of the API.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import agent_client, style_prefs
from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..models import ComprehensionProfile, PersonalizedSummaryCache, User

router = APIRouter(prefix="/api/comprehension", tags=["comprehension"])

DEFAULT_PROFILE = {
    "reading_level": "general", "style_notes": [], "understanding_history": [],
    "style_scores": {}, "style_emphasis": [],
}
READING_LEVELS = {"general", "beginner", "advanced"}
UNDERSTANDING_LEVELS = {"low", "medium", "high"}


def _normalize_reading_level(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in READING_LEVELS else "general"


def _coerce_scores(raw) -> list[int]:
    """Keep only numeric scores in [0,100] — drops transcripts/answers/garbage the
    model may have stuffed into understanding_history."""
    out: list[int] = []
    for item in raw if isinstance(raw, list) else []:
        val = item.get("score") if isinstance(item, dict) else item
        try:
            n = int(round(float(val)))
        except (TypeError, ValueError):
            continue
        out.append(max(0, min(100, n)))
    return out


def _ensure_enabled() -> None:
    if not settings.hermes_enabled:
        raise HTTPException(503, "Agent features are off. Set HERMES_ENABLED=true and run the Hermes sidecar.")


async def _load_profile(session: AsyncSession, user_id: str) -> tuple[ComprehensionProfile | None, dict]:
    row = await session.get(ComprehensionProfile, user_id)
    if row is None:
        return None, dict(DEFAULT_PROFILE)
    scores = style_prefs.normalize(getattr(row, "style_scores", None) or "{}")
    return row, {
        "reading_level": row.reading_level,
        "style_notes": json.loads(row.style_notes or "[]"),
        "understanding_history": json.loads(row.understanding_history or "[]"),
        "style_scores": scores,
        # Ranked style instructions (top + a blended 2nd) the agent should honor.
        "style_emphasis": style_prefs.emphasis_phrases(scores),
    }


async def _save_profile(session: AsyncSession, user_id: str,
                        row: ComprehensionProfile | None, profile: dict) -> None:
    reading_level = _normalize_reading_level(profile.get("reading_level"))
    style_notes = json.dumps([str(s) for s in (profile.get("style_notes") or [])][:20])
    history = json.dumps(_coerce_scores(profile.get("understanding_history"))[-20:])
    # style_scores: use the explicit value when provided (style controls), else
    # preserve whatever's already stored (e.g. the assess step doesn't touch it).
    if "style_scores" in profile:
        style_scores = json.dumps(style_prefs.normalize(profile.get("style_scores")))
    elif row is not None:
        style_scores = getattr(row, "style_scores", None) or "{}"
    else:
        style_scores = "{}"
    if row is None:
        session.add(ComprehensionProfile(
            user_id=user_id, reading_level=reading_level,
            style_notes=style_notes, understanding_history=history,
            style_scores=style_scores,
        ))
    else:
        row.reading_level = reading_level
        row.style_notes = style_notes
        row.understanding_history = history
        row.style_scores = style_scores
    await session.commit()


# Cap the transcript sent to the agent. A few-question quiz / level-adapted summary
# needs a representative chunk, not a whole 100k+ token transcript — sending the full
# thing blows past Gemini's free-tier input-token-per-minute limit. ~24k chars ≈ 6k tokens.
_AGENT_MAX_TRANSCRIPT_CHARS = 24000


def _check_transcript(text: str) -> str:
    t = (text or "").strip()
    if len(t) < settings.transcript_min_chars:
        raise HTTPException(422, "Transcript is too short.")
    if len(t) > _AGENT_MAX_TRANSCRIPT_CHARS:
        t = t[:_AGENT_MAX_TRANSCRIPT_CHARS] + "\n\n[transcript truncated for the quiz]"
    return t


# --- Personalized-summary cache: generate once per (user, content), reuse on re-view.
def _content_hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _profile_sig(profile: dict) -> str:
    """Hash of the style-relevant profile fields — changes when the user's prefs change,
    which invalidates (regenerates) the cached personalized summary."""
    key = json.dumps(
        {
            "reading_level": profile.get("reading_level", ""),
            "style_notes": sorted(str(s) for s in (profile.get("style_notes") or [])),
            "style_scores": style_prefs.sig(profile.get("style_scores") or {}),
        },
        sort_keys=True,
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def _load_cached_summary(session: AsyncSession, user_id: str, chash: str, psig: str) -> str | None:
    row = await session.get(PersonalizedSummaryCache, (user_id, chash))
    return row.summary if (row is not None and row.profile_sig == psig) else None


async def _save_cached_summary(session: AsyncSession, user_id: str, chash: str, psig: str, summary: str) -> None:
    row = await session.get(PersonalizedSummaryCache, (user_id, chash))
    if row is None:
        session.add(PersonalizedSummaryCache(user_id=user_id, content_hash=chash, profile_sig=psig, summary=summary))
    else:
        row.profile_sig = psig
        row.summary = summary
    await session.commit()


class SummaryIn(BaseModel):
    transcript: str
    summary_type: str = "detailed"
    force: bool = False  # bypass the cache + regenerate


class QuizIn(BaseModel):
    transcript: str
    num_questions: int = Field(5, ge=1, le=15)


class AssessIn(BaseModel):
    transcript: str
    answers: list[dict]  # [{"question": "...", "type": "comprehension"|"feedback", "answer": "..."}]


class StyleIn(BaseModel):
    value: str | None = None              # a style key from style_prefs.TAXONOMY
    delta: float = style_prefs.BUMP       # how hard to nudge it
    note: str | None = None               # optional free-text preference


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _, profile = await _load_profile(session, user.id)
    return profile


@router.post("/summary")
async def make_adaptive_summary(
    body: SummaryIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _ensure_enabled()
    transcript = _check_transcript(body.transcript)
    _, profile = await _load_profile(session, user.id)
    chash = _content_hash(body.summary_type, transcript)
    psig = _profile_sig(profile)
    if not body.force:
        cached = await _load_cached_summary(session, user.id, chash, psig)
        if cached is not None:
            return {"summary": cached, "profile_used": profile, "cached": True}
    try:
        summary = await agent_client.adaptive_summary(user.id, transcript, profile, body.summary_type)
    except agent_client.AgentError as exc:
        raise HTTPException(502, f"Agent error: {exc}")
    await _save_cached_summary(session, user.id, chash, psig, summary)
    return {"summary": summary, "profile_used": profile, "cached": False}


@router.post("/quiz")
async def make_quiz(
    body: QuizIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _ensure_enabled()
    transcript = _check_transcript(body.transcript)
    try:
        return await agent_client.generate_questions(user.id, transcript, body.num_questions)
    except agent_client.AgentError as exc:
        raise HTTPException(502, f"Agent error: {exc}")


@router.post("/assess")
async def assess(
    body: AssessIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _ensure_enabled()
    transcript = _check_transcript(body.transcript)
    row, profile = await _load_profile(session, user.id)
    try:
        result = await agent_client.assess_and_adapt(user.id, transcript, body.answers, profile)
    except agent_client.AgentError as exc:
        raise HTTPException(502, f"Agent error: {exc}")
    lvl = str(result.get("understanding_level") or "").strip().lower()
    result["understanding_level"] = lvl if lvl in UNDERSTANDING_LEVELS else "medium"
    updated = result.get("updated_profile")
    if isinstance(updated, dict):
        await _save_profile(session, user.id, row, updated)  # persist the adaptation
    return result


@router.get("/style/options")
async def style_options(user: User = Depends(get_current_user)):
    """The selectable styles for the direct-control chips."""
    return {"options": style_prefs.options()}


@router.post("/style")
async def set_style(
    body: StyleIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Directly nudge the user's style (no quiz needed). Bumps the chosen style
    (decaying the rest so it can blend/shift) and/or adds a free-text note, then
    persists. The personalized summary regenerates because the profile changed."""
    row, profile = await _load_profile(session, user.id)
    changed = False
    if body.value:
        if not style_prefs.valid_value(body.value):
            raise HTTPException(422, f"Unknown style: {body.value}")
        profile["style_scores"] = style_prefs.bump(
            profile.get("style_scores") or {}, body.value, body.delta
        )
        changed = True
    if body.note and body.note.strip():
        profile["style_notes"] = list(profile.get("style_notes") or []) + [body.note.strip()]
        changed = True
    if not changed:
        raise HTTPException(422, "Provide a style 'value' or a 'note'.")
    await _save_profile(session, user.id, row, profile)
    _, fresh = await _load_profile(session, user.id)
    return {"ok": True, "profile": fresh}
