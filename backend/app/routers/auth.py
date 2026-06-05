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
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..email import send_email
from ..models import ClientType, EmailVerification, PasswordResetCode, Session, User, UserStatus
from ..security import (
    create_access_token,
    dummy_verify,
    generate_otp,
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
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)
    password: str = Field(min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


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


async def _send_email_otp(session: AsyncSession, user: User, background: BackgroundTasks) -> None:
    """Invalidate any outstanding codes, mint a fresh 6-digit OTP (hashed at
    rest), and queue the verification email (printed to the log in dev)."""
    await session.execute(
        update(EmailVerification)
        .where(EmailVerification.user_id == user.id, EmailVerification.used_at.is_(None))
        .values(used_at=utcnow())
    )
    code = generate_otp()
    session.add(
        EmailVerification(
            user_id=user.id,
            code_hash=hash_token(code),
            expires_at=utcnow() + timedelta(minutes=settings.email_otp_ttl_minutes),
        )
    )
    background.add_task(
        send_email,
        user.email,
        "Your verification code",
        f"Your Video Synopsis verification code is: {code}\n\n"
        f"It expires in {settings.email_otp_ttl_minutes} minutes.",
    )


# --- Endpoints ---------------------------------------------------------------

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, background: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    email = normalize_email(body.email)

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")

    # Beta cap: stop new signups once we hit the user limit.
    user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    if user_count >= settings.max_users:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "We've reached our beta user limit. Please check back soon.",
        )

    # Account starts UNVERIFIED (no auto-login). The client must confirm the
    # emailed OTP at /auth/verify-email, which then logs the user in.
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        status=UserStatus.active.value,
        email_verified_at=None,
    )
    session.add(user)
    try:
        await session.flush()  # triggers the unique-email INSERT
    except IntegrityError:
        # Race: another signup created the same email between the check and flush.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Account already exists")

    await _send_email_otp(session, user, background)
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
    if user.email_verified_at is None:
        # Distinct 403 so the client can route the user to the verify-email page.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please verify your email to continue.")

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
async def logout(request: Request, session: AsyncSession = Depends(get_session)):
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
    # Clear cookies on the response we actually RETURN. (Mutating an injected
    # Response and then returning a different one drops the Set-Cookie headers.)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(resp)
    return resp


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user.token_version += 1  # invalidates every live access token (B4)
    await session.execute(
        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(resp)
    return resp


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/verify-email", response_model=UserOut)
async def verify_email(body: VerifyEmailIn, response: Response, session: AsyncSession = Depends(get_session)):
    """Confirm the signup OTP. On success the email is marked verified and the
    user is signed in (cookies set)."""
    email = normalize_email(body.email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired code.")
    if user.email_verified_at is not None:
        # Already verified — sign in (idempotent).
        await _issue_session(session, user, response)
        await session.commit()
        return UserOut(id=user.id, email=user.email, status=user.status)

    row = (
        await session.execute(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id, EmailVerification.used_at.is_(None))
            .order_by(EmailVerification.created_at.desc())
        )
    ).scalars().first()
    if row is None or row.expires_at < utcnow() or row.attempts >= settings.email_otp_max_attempts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired code. Request a new one.")

    if hash_token(body.code.strip()) != row.code_hash:
        row.attempts += 1
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect code.")

    row.used_at = utcnow()
    user.email_verified_at = utcnow()
    await _issue_session(session, user, response)  # verified -> sign in
    await session.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: EmailIn, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
):
    """Re-send the signup OTP. Always 202 (no account enumeration)."""
    email = normalize_email(body.email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None and user.email_verified_at is None:
        await _send_email_otp(session, user, background)
        await session.commit()
    return {"status": "accepted"}


@router.post("/change-password", response_model=UserOut)
async def change_password(
    body: ChangePasswordIn,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Change password for the signed-in user.

    Verifies the current password, then rotates everything: bump token_version
    (kills every live access token), revoke all refresh sessions (logs out other
    devices), and issue a fresh session so THIS device stays signed in.
    """
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different")

    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # invalidate every existing access token
    await session.execute(
        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    # Re-issue a session for the current device with the new token_version.
    await _issue_session(session, user, response)
    await session.commit()
    return UserOut(id=user.id, email=user.email, status=user.status)


@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: EmailIn, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
):
    """Email a 6-digit reset code. Always 202 (no account enumeration)."""
    email = normalize_email(body.email)
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is not None and user.status == UserStatus.active.value:
        # Invalidate any outstanding codes, then issue a fresh one.
        await session.execute(
            update(PasswordResetCode)
            .where(PasswordResetCode.user_id == user.id, PasswordResetCode.used_at.is_(None))
            .values(used_at=utcnow())
        )
        code = generate_otp()
        session.add(
            PasswordResetCode(
                user_id=user.id,
                code_hash=hash_token(code),
                expires_at=utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
        await session.commit()
        background.add_task(
            send_email,
            email,
            "Your password reset code",
            f"Your Video Synopsis password reset code is: {code}\n\n"
            f"It expires in {settings.password_reset_ttl_minutes} minutes. "
            "If you didn't request this, you can ignore this email.",
        )

    return {"status": "accepted"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetIn, session: AsyncSession = Depends(get_session)):
    """Verify the emailed reset code and set a new password (kills all sessions)."""
    email = normalize_email(body.email)
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired code.")

    row = (
        await session.execute(
            select(PasswordResetCode)
            .where(PasswordResetCode.user_id == user.id, PasswordResetCode.used_at.is_(None))
            .order_by(PasswordResetCode.created_at.desc())
        )
    ).scalars().first()
    if row is None or row.expires_at < utcnow() or row.attempts >= settings.email_otp_max_attempts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired code. Request a new one.")

    if hash_token(body.code.strip()) != row.code_hash:
        row.attempts += 1
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect code.")

    row.used_at = utcnow()
    user.password_hash = hash_password(body.password)
    user.token_version += 1  # kill existing access tokens
    await session.execute(
        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(resp)
    return resp
