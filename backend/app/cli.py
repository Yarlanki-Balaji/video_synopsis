"""Tiny admin CLI for local/beta operations.

Create the database schema (run once on a fresh production database):

    python -m app.cli init-db

Revoke a user (de-allowlist; bumps token_version so their tokens die now):

    python -m app.cli revoke someone@example.com
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_models
from .models import User, UserStatus
from .security import normalize_email


async def _ensure_schema() -> None:
    # Dev only: create tables on demand. Production schema is managed by migrations.
    if not settings.is_production:
        await init_models()


async def revoke_user(email: str) -> None:
    email = normalize_email(email)
    await _ensure_schema()
    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            print(f"No user with email {email}")
            return
        user.status = UserStatus.revoked.value
        user.token_version += 1
        await session.commit()
        print(f"Revoked {email}")


async def init_db() -> None:
    await init_models()
    print("Schema is ready (tables created or already present).")


def main() -> None:
    args = sys.argv[1:]
    if args == ["init-db"]:
        asyncio.run(init_db())
        return
    if len(args) == 2 and args[0] == "revoke":
        asyncio.run(revoke_user(args[1]))
        return
    print(__doc__)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
