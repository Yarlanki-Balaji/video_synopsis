"""SQLAlchemy models.

Schema:
  - users:       identity + status + token_version
  - sessions:    refresh tokens, hashed + rotated + family for reuse-detect
  - jobs:        summarization jobs, per-user history
  - summaries:   content-bound cache
  - daily_usage: quota counters
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
    active = "active"
    revoked = "revoked"


class ClientType(str, enum.Enum):
    web = "web"
    extension = "extension"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # password_hash is nullable — email-only sign-in creates accounts without passwords.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.active.value)
    # Bumped on logout-all to invalidate live access tokens.
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


# --- M2: job engine + summaries + usage ------------------------------------

class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class Job(Base):
    """A summarization job. Postgres is the source of truth."""

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
    # cached and OVERWRITES the shared Summary rows in place.
    force: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.queued.value, index=True)
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Lease: which runner owns the job + a fencing token (lease_count).
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Summary(Base):
    """Content-bound, per-type cache + results. Reused across requests only
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
    """Postgres-authoritative usage counters. scope = 'global' or 'user:<id>'."""

    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("scope", "day", name="uq_usage_scope_day"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    day: Mapped[str] = mapped_column(String(10))    # YYYY-MM-DD (UTC)
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)


class ServiceState(Base):
    """Singleton row (id=1) holding circuit-breaker state."""

    __tablename__ = "service_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    breaker_open_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
