"""Password hashing, opaque-token hashing, and JWT mint/verify.

- Passwords: bcrypt (B1), capped at 72 bytes (bcrypt ignores the rest).
- Opaque tokens (refresh / reset): random, stored only as sha256 (B3).
- Access tokens: JWT HS256 with the algorithm PINNED and exp/aud/sub required (B2).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings

# A fixed hash to verify against when a login email is unknown, so response
# timing doesn't reveal whether an account exists.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt())


def utcnow() -> datetime:
    """Naive UTC 'now' — matches the naive UTC columns in models.py."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    """Single choke point for email normalization (case/space folding)."""
    return email.strip().casefold()


# --- Passwords ---------------------------------------------------------------

def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def dummy_verify() -> None:
    """Burn ~one bcrypt round to equalize timing on the unknown-user path."""
    bcrypt.checkpw(b"timing-equalizer", _DUMMY_HASH)


# --- Opaque tokens -----------------------------------------------------------

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_otp() -> str:
    """A 6-digit numeric one-time code (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


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
