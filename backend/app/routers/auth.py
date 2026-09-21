"""Auth endpoints — email-only sign-in.

Routes (prefix /auth):
  POST /signin   enter any email → auto-create/retrieve user → set session cookies
  POST /logout   revoke current session family + clear cookies
  GET  /me       current user info
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..models import ClientType, Session, User, UserStatus
from ..security import (
    create_access_token,
    generate_token,
    hash_token,
    normalize_email,
    utcnow,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/auth"  # refresh cookie is only sent to /auth/* routes


# --- Schemas -----------------------------------------------------------------

class SigninIn(BaseModel):
    email: EmailStr


class UserOut(BaseModel):
    id: str
    email: str
    status: str


# --- Cookie helpers ----------------------------------------------------------

def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE, access,
        httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite,
        max_age=settings.access_token_ttl_minutes * 60, path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh,
        httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_ttl_days * 86400, path=REFRESH_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    common = dict(secure=settings.cookie_secure, samesite=settings.cookie_samesite, httponly=True)
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **common)


async def _issue_session(
    db: AsyncSession, user: User, response: Response,
    *, family_id: str | None = None, client_type: str = ClientType.web.value,
) -> None:
    """Mint a new access token + refresh session and set both cookies."""
    raw_refresh = generate_token()
    fam = family_id or generate_token(16)
    db.add(
        Session(
            user_id=user.id,
            family_id=fam,
            token_hash=hash_token(raw_refresh),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            client_type=client_type,
        )
    )
    access = create_access_token(user.id, user.token_version, audience=client_type)
    _set_auth_cookies(response, access, raw_refresh)


# --- Endpoints ---------------------------------------------------------------

@router.post("/signin", response_model=UserOut)
async def signin(body: SigninIn, response: Response, db: AsyncSession = Depends(get_session)):
    """Email-only sign-in: enter any email address → instantly signed in.
    Creates a new user account on first use; retrieves the existing one on return visits.
    No password, no OTP, no verification step required.
    """
    email = normalize_email(body.email)

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None:
        # First time this email signs in — create an account automatically.
        user = User(
            email=email,
            status=UserStatus.active.value,
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # Race condition: another request created the user just now. Fetch it.
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one()

    if user.status != UserStatus.active.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is not active.")

    await _issue_session(db, user, response)
    await db.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: AsyncSession = Depends(get_session)):
    """Revoke the current refresh session family and clear auth cookies."""
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        row = (
            await db.execute(select(Session).where(Session.token_hash == hash_token(raw)))
        ).scalar_one_or_none()
        if row is not None:
            await db.execute(
                update(Session)
                .where(Session.family_id == row.family_id, Session.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            await db.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(resp)
    return resp


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, status=user.status)
