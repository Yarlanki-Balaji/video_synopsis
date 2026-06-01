"""Shared FastAPI dependencies."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import User, UserStatus
from .security import decode_access_token

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    """Resolve the caller from the access-token cookie (web) or Bearer (extension).

    Enforces, on EVERY request (B4/B5): valid signature + pinned alg + audience,
    user exists and status == active, and token_version still matches.
    """
    cookie = request.cookies.get("access_token")
    header = request.headers.get("Authorization", "")

    if cookie:
        token, audience = cookie, "web"
    elif header.lower().startswith("bearer "):
        token, audience = header[7:], "extension"
    else:
        raise _UNAUTH

    try:
        payload = decode_access_token(token, audience=audience)
    except jwt.PyJWTError:
        raise _UNAUTH

    user = await session.get(User, payload.get("sub"))
    if user is None or user.status != UserStatus.active.value:
        raise _UNAUTH
    if int(payload.get("tv", -1)) != user.token_version:
        raise _UNAUTH

    return user
