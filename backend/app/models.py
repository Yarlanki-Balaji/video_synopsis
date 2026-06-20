"""SQLAlchemy models for auth & accounts (M1).

Schema (build guide Part B, minus the invite gate — signup is open for a
private-network deployment):
  - users:           identity + allowlist status + token_version (B4/B5)
  - sessions:        refresh tokens, hashed + rotated + family for reuse-detect (B3)
  - password_resets: single-use, short-lived, hashed at rest (B6)
"""
from __future__ import annotations

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .security import utcnow


def _uuid() -> str:
    return uuid4().hex


class UserStatus(str, enum.Enum):
    invited = "invited"
    active = "active"
    revoked = "revoked"


class ClientType(str, enum.Enum):
    web = "web"
    extension = "extension"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.active.value)
    # Bumped on logout-all / reset / de-allowlist to invalidate live access tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Session(Base):
    """One refresh token. Rotated on every use; a reused token revokes the family."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    replaced_by_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    client_type: Mapped[str] = mapped_column(String(16), default=ClientType.web.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PendingSignup(Base):
    """A signup awaiting email verification. The real User row is NOT created
    until the emailed OTP is confirmed — so a wrong or abandoned code never
    leaves an account behind (and never consumes a beta slot). One per email;
    the hashed password lives here only until verification."""

    __tablename__ = "pending_signups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordResetCode(Base):
    """Single-use, short-lived 6-digit OTP for password reset. Like
    EmailVerification: hashed, expiring, attempt-capped, and looked up per user
    (code_hash is NOT unique — short codes can collide across users)."""

    __tablename__ = "password_reset_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --- M2: job engine + summaries + usage ------------------------------------

class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class Job(Base):
    """A summarization job. Postgres is the source of truth (E3)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    source: Mapped[str] = mapped_column(String(16), default="paste")  # paste|api|extension
    video_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    transcript_sha256: Mapped[str] = mapped_column(String(64), index=True)
    transcript: Mapped[str] = mapped_column(Text)            # capped text to summarize
    lang: Mapped[str] = mapped_column(String(8), default="en")
    summary_types: Mapped[str] = mapped_column(String(255))  # comma-joined sorted
    complete_notes: Mapped[bool] = mapped_column(Boolean, default=False)
    # Regenerate: when set, the worker re-generates the requested types even if
    # cached and OVERWRITES the shared Summary rows in place — so a regenerate
    # never deletes another user's completed result (no empty window, no loss).
    force: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.queued.value, index=True)
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Lease (E3/E4): which runner owns the job + a fencing token (lease_count).
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Summary(Base):
    """Content-bound, per-type cache + results (G4). Reused across requests only
    when the transcript hash matches — safe sharing, no poisoning."""

    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint("transcript_sha256", "type", "lang", name="uq_summary_content"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    transcript_sha256: Mapped[str] = mapped_column(String(64), index=True)
    video_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(16))   # brief|detailed|bullets|chapters|eli5|notes
    lang: Mapped[str] = mapped_column(String(8), default="en")
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="paste")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DailyUsage(Base):
    """Postgres-authoritative usage counters (F5). scope = 'global' or 'user:<id>'."""

    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("scope", "day", name="uq_usage_scope_day"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[str] = mapped_column(String(10))    # YYYY-MM-DD (UTC)
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)


class ServiceState(Base):
    """Singleton row (id=1) holding circuit-breaker state (F5)."""

    __tablename__ = "service_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    breaker_open_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


# --- Hermes agent: per-user comprehension features -------------------------

class ComprehensionProfile(Base):
    """Per-user comprehension profile — the adaptive 'memory' that tailors summaries
    to how well a user understands a topic. Created/updated by the assess step
    (POST /api/comprehension/assess). JSON values are stored as TEXT for SQLite +
    Postgres portability."""

    __tablename__ = "comprehension_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reading_level: Mapped[str] = mapped_column(String(16), default="general")  # general|beginner|advanced
    style_notes: Mapped[str] = mapped_column(Text, default="[]")               # JSON array of strings
    understanding_history: Mapped[str] = mapped_column(Text, default="[]")     # JSON array of recent scores
    # Structured style preferences: JSON dict of style value -> weight. Driven by the
    # direct style controls (decayed + mixed); complements the free-text style_notes.
    style_scores: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PersonalizedSummaryCache(Base):
    """Caches the per-user 'Personalized for you' summary so it's generated ONCE per
    (user, content) instead of on every page view. `profile_sig` is a hash of the user's
    style-relevant profile fields — a mismatch means the profile changed since caching,
    so the entry is treated as stale and regenerated."""

    __tablename__ = "personalized_summaries"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of input content
    profile_sig: Mapped[str] = mapped_column(String(64))                     # sha256 of profile style fields
    summary: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
