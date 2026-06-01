"""Database engine, session factory, and optional Valkey client.

Times are stored as naive UTC for portability across SQLite (local dev) and
Postgres (prod). Use security.utcnow() everywhere.
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional

import ssl as ssl_lib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import redis.asyncio as redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    """Build the async engine, translating managed-Postgres SSL params (asyncpg
    uses an `ssl` connect arg, not the libpq `?sslmode=` URL param)."""
    url = settings.effective_database_url
    connect_args: dict = {}
    if url.startswith("postgresql"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)  # asyncpg doesn't accept it
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = (
                ssl_lib.create_default_context(cafile=settings.database_ssl_ca)
                if settings.database_ssl_ca
                else ssl_lib.create_default_context()
            )
    elif url.startswith("sqlite"):
        connect_args["timeout"] = 30
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


_is_sqlite = settings.effective_database_url.startswith("sqlite")

engine = _make_engine()

if _is_sqlite:
    # WAL + a busy timeout let the background worker and web requests write
    # concurrently without "database is locked" errors in local dev.
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

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
