"""FastAPI application entrypoint.

Run locally:  uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_models
from .routers import auth, health

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cookie config sanity (applies everywhere).
    if settings.cookie_samesite.lower() not in {"lax", "strict", "none"}:
        raise RuntimeError("COOKIE_SAMESITE must be one of: lax, strict, none")
    if settings.cookie_samesite.lower() == "none" and not settings.cookie_secure:
        raise RuntimeError("SameSite=None requires Secure cookies (HTTPS)")
    if "*" in settings.cors_origin_list:
        raise RuntimeError("CORS_ORIGINS must be explicit origins, not '*'")

    # Production hardening.
    if settings.is_production:
        if settings.jwt_secret == "dev-insecure-secret-change-me" or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be a strong (>=32 char) value in production")
        if not settings.resend_api_key:
            # Console email mode logs reset tokens — unsafe in production.
            raise RuntimeError("RESEND_API_KEY is required in production")

    # Dev convenience: auto-create tables. Production uses Alembic migrations.
    if not settings.is_production:
        await init_models()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """CSRF defence for cookie auth (B7): state-changing browser requests must
    carry an Origin we trust. Bearer-token (extension) requests are exempt —
    they aren't sent automatically by the browser, so they can't be forged.
    """
    if request.method not in SAFE_METHODS:
        has_cookie = "access_token" in request.cookies or "refresh_token" in request.cookies
        is_bearer = request.headers.get("Authorization", "").lower().startswith("bearer ")
        # Only a true extension request (Bearer token, NO auth cookie) is exempt.
        # Any request carrying our cookies must prove a trusted Origin — a forged
        # cross-site request can't drop the victim's cookie by adding a Bearer header.
        is_extension = is_bearer and not has_cookie
        if not is_extension:
            origin = request.headers.get("Origin")
            if origin is None or origin not in settings.cors_origin_list:
                return JSONResponse(status_code=403, content={"detail": "CSRF origin check failed"})
    return await call_next(request)


app.include_router(health.router)
app.include_router(auth.router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs", "health": "/healthz"}
