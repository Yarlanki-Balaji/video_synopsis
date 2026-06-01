"""Lazy connections to Aiven Postgres and Valkey.

Connections are created only when the corresponding URL is configured, so the
service runs locally with no database. The check_* helpers return:
  - True  -> configured and reachable
  - False -> configured but unreachable
  - None  -> not configured yet
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import settings

_engine: Optional[AsyncEngine] = None
_valkey: Optional[redis.Redis] = None


def get_engine() -> Optional[AsyncEngine]:
    """Create (once) and return the async SQLAlchemy engine, or None if unconfigured."""
    global _engine
    if settings.database_url and _engine is None:
        url = settings.database_url
        # SQLAlchemy needs the async driver in the scheme.
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=0)
    return _engine


def get_valkey() -> Optional[redis.Redis]:
    """Create (once) and return the Valkey/Redis client, or None if unconfigured."""
    global _valkey
    if settings.valkey_url and _valkey is None:
        _valkey = redis.from_url(settings.valkey_url, decode_responses=True)
    return _valkey


async def check_database() -> Optional[bool]:
    engine = get_engine()
    if engine is None:
        return None
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
