"""Tiny admin CLI for local/beta operations.

Create an invite (prints the token + signup link; also "emails" it via the
configured sender — console by default):

    python -m app.cli invite someone@example.com

Revoke a user (de-allowlist; bumps token_version so their tokens die now):

    python -m app.cli revoke someone@example.com
"""
from __future__ import annotations

import asyncio
import sys
from datetime import timedelta

from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_models
from .email import send_email
from .models import Invite, User, UserStatus
from .security import generate_token, hash_token, normalize_email, utcnow


async def _ensure_schema() -> None:
    # Dev only: create tables on demand. Production schema is managed by migrations.
    if not settings.is_production:
        await init_models()


async def create_invite(email: str) -> None:
    email = normalize_email(email)
    await _ensure_schema()
    token = generate_token()
    async with SessionLocal() as session:
        session.add(
            Invite(
                email=email,
                token_hash=hash_token(token),
                expires_at=utcnow() + timedelta(hours=settings.invite_ttl_hours),
            )
        )
        await session.commit()

    link = f"{settings.public_app_url}/signup?email={email}&invite={token}"
    await send_email(email, "You're invited to Video Synopsis", f"Sign up:\n{link}")
    print(f"INVITE for {email}")
    print(f"  token: {token}")
    print(f"  link:  {link}")


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


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"invite", "revoke"}:
        print(__doc__)
        raise SystemExit(1)
    command, arg = sys.argv[1], sys.argv[2]
    if command == "invite":
        asyncio.run(create_invite(arg))
    else:
        asyncio.run(revoke_user(arg))


if __name__ == "__main__":
    main()
