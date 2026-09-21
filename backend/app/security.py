"""Password hashing, opaque-token hashing, and JWT mint/verify.

- Opaque tokens (refresh): random, stored only as sha256.
- Access tokens: JWT HS256 with the algorithm PINNED and exp/aud/sub required.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def utcnow() -> datetime:
    """Naive UTC 'now' — matches the naive UTC columns in models.py."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    """Single choke point for email normalization (case/space folding)."""
    return email.strip().casefold()


# --- Opaque tokens -----------------------------------------------------------

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Access JWT --------------------------------------------------------------

def create_access_token(user_id: str, token_version: int, audience: str = "web") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tv": token_version,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, audience: str = "web") -> dict:
    """Raises jwt.PyJWTError on any problem (bad sig, wrong alg, exp, aud)."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],  # PINNED — blocks alg=none forgery
        audience=audience,
        options={"require": ["exp", "aud", "sub"]},
    )
