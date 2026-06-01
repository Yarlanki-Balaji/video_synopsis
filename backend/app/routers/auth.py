"""Auth & accounts endpoints (B1–B7).

Routes (prefix /auth):
  POST /signup                 create account (email + password), auto-login
  POST /login                  email + password -> set cookies
  POST /refresh                rotate refresh token (reuse -> revoke family)
  POST /logout                 revoke current session family + clear cookies
  POST /logout-all             bump token_version + revoke all sessions
  GET  /me                     current user
  POST /request-password-reset always 202 (no user enumeration)
  POST /reset-password         consume reset token + force re-login
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..email import send_email
from ..models import ClientType, PasswordReset, Session, User, UserStatus
from ..security import (
    create_access_token,
    dummy_verify,
    generate_token,
    hash_password,
    hash_token,
    normalize_email,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/auth"  # refresh cookie is only sent to /auth/* routes


# --- Schemas -----------------------------------------------------------------

class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


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
    # Attributes must match the originals or the browser won't clear the cookie
    # (notably under SameSite=None; Secure in cross-site production).
    common = dict(secure=settings.cookie_secure, samesite=settings.cookie_samesite, httponly=True)
    response.delete_cookie(ACCESS_COOKIE, path="/", **common)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, **common)


async def _issue_session(
    session: AsyncSession, user: User, response: Response,
    *, family_id: str | None = None, client_type: str = ClientType.web.value,
) -> None:
    """Mint a new access token + refresh session and set both cookies."""
    raw_refresh = generate_token()
    fam = family_id or generate_token(16)
    session.add(
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

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, response: Response, session: AsyncSession = Depends(get_session)):
    email = normalize_email(body.email)

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        status=UserStatus.active.value,
        email_verified_at=utcnow(),
    )
    session.add(user)
    try:
        await session.flush()  # triggers the unique-email INSERT
    except IntegrityError:
        # Race: another signup created the same email between the check and flush.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")

    await _issue_session(session, user, response)
    await session.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, session: AsyncSession = Depends(get_session)):
    email = normalize_email(body.email)
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    # Password is checked BEFORE the status branch, so the 403 below is only
    # reachable with valid credentials -> it is not an account-enumeration oracle.
    if user is None:
        dummy_verify()  # equalize timing for unknown accounts
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.status != UserStatus.active.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")

    await _issue_session(session, user, response)
    await session.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/refresh", response_model=UserOut)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")

    row = (
        await session.execute(select(Session).where(Session.token_hash == hash_token(raw)))
    ).scalar_one_or_none()

    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        _clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    async def _revoke_family_and_fail() -> None:
        await session.execute(
            update(Session).where(Session.family_id == row.family_id, Session.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await session.commit()
        _clear_auth_cookies(response)

    # Fast path: an already-consumed token is being replayed -> theft (B3).
    if row.used_at is not None:
        await _revoke_family_and_fail()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected")

    user = await session.get(User, row.user_id)
    if user is None or user.status != UserStatus.active.value:
        _clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")

    # Atomically consume this token. If we lose the race (rowcount 0), another
    # request already rotated it -> treat as reuse and revoke the family.
    new_id = uuid4().hex
    raw_new = generate_token()
    consumed = await session.execute(
        update(Session).where(Session.id == row.id, Session.used_at.is_(None))
        .values(used_at=utcnow(), replaced_by_id=new_id)
    )
    if consumed.rowcount != 1:
        await _revoke_family_and_fail()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected")

    session.add(
        Session(
            id=new_id,
            user_id=user.id,
            family_id=row.family_id,
            token_hash=hash_token(raw_new),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            client_type=row.client_type,
        )
    )
    access = create_access_token(user.id, user.token_version, audience=row.client_type)
    _set_auth_cookies(response, access, raw_new)
    await session.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    # Plain logout revokes the refresh family + clears cookies. The current
    # access token stays valid until exp (<=30 min); use /logout-all to kill it
    # immediately (bumps token_version).
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        row = (
            await session.execute(select(Session).where(Session.token_hash == hash_token(raw)))
        ).scalar_one_or_none()
        if row is not None:
            await session.execute(
                update(Session).where(Session.family_id == row.family_id, Session.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            await session.commit()
    _clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(response: Response, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user.token_version += 1  # invalidates every live access token (B4)
    await session.execute(
        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    _clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: EmailIn, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
):
    email = normalize_email(body.email)
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    # Always return the same 202. The email send is queued to a background task
    # so response latency doesn't reveal whether the account exists.
    if user is not None and user.status == UserStatus.active.value:
        # Invalidate any prior outstanding reset tokens for this user.
        await session.execute(
            update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
            .values(used_at=utcnow())
        )
        raw = generate_token()
        session.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
        await session.commit()
        link = f"{settings.public_app_url}/reset-password?token={raw}"
        background.add_task(
            send_email, email, "Reset your password",
            f"Reset link (valid {settings.password_reset_ttl_minutes} min):\n{link}",
        )

    return {"status": "accepted"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetIn, response: Response, session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(select(PasswordReset).where(PasswordReset.token_hash == hash_token(body.token)))
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    # Atomic single-use claim.
    claimed = await session.execute(
        update(PasswordReset).where(PasswordReset.id == row.id, PasswordReset.used_at.is_(None))
        .values(used_at=utcnow())
    )
    if claimed.rowcount != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user = await session.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user.password_hash = hash_password(body.password)
    user.token_version += 1  # kill existing access tokens
    # Force re-login everywhere.
    await session.execute(
        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    _clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
