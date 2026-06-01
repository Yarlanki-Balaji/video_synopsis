"""Database engine, session factory, and optional Valkey client.

Times are stored as naive UTC for portability across SQLite (local dev) and
Postgres (prod). Use security.utcnow() everywhere.
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.effective_database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables for local dev. Production uses Alembic migrations (later)."""
    from . import models  # noqa: F401  (register mappers before create_all)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


_valkey: Optional[redis.Redis] = None


def get_valkey() -> Optional[redis.Redis]:
    global _valkey
    if settings.valkey_url and _valkey is None:
        _valkey = redis.from_url(settings.valkey_url, decode_responses=True)
    return _valkey


async def check_database() -> Optional[bool]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_valkey() -> Optional[bool]:
    client = get_valkey()
    if client is None:
        return None
    try:
        return bool(await client.ping())
    except Exception:
        return False
