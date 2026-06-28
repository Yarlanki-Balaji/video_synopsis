"""FastAPI application entrypoint.

Run locally:  uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_models
from .jobs import start_worker, stop_worker
from .routers import auth, health, summarize

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

    # Production hardening — fail fast at boot rather than mis-serving later.
    if settings.is_production:
        if settings.jwt_secret == "dev-insecure-secret-change-me" or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be a strong (>=32 char) value in production")
        # A real email provider is required (console mode logs reset tokens). Brevo
        # OR Resend is fine — email.py prefers Brevo when both are configured.
        has_brevo = bool(settings.brevo_api_key and settings.brevo_sender_email)
        if not (settings.resend_api_key or has_brevo):
            raise RuntimeError(
                "An email provider is required in production: set RESEND_API_KEY, "
                "or BREVO_API_KEY + BREVO_SENDER_EMAIL"
            )
        # Require a real Postgres URL: without it the app silently falls back to a
        # SQLite file on ephemeral disk and loses ALL data on every restart/redeploy.
        if not settings.database_url or settings.effective_database_url.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL (Postgres) is required in production")
        # Don't ship deterministic [stub] summaries: refuse to start with no LLM key.
        if settings.effective_llm_provider == "stub":
            raise RuntimeError("No LLM key configured: set GEMINI_API_KEY or GROQ_API_KEY in production")
        # On a cloud IP the direct caption fetch is blocked, so prod needs the
        # managed provider — and it's useless without its key.
        if settings.transcript_provider == "managed" and not settings.transcript_api_key:
            raise RuntimeError("TRANSCRIPT_PROVIDER=managed requires TRANSCRIPT_API_KEY")
        # The CSRF guard rejects any state-changing request whose Origin isn't in
        # CORS_ORIGINS. A leftover localhost default in production silently 403s
        # every login/signup/summarize — so fail fast at boot instead.
        if any("localhost" in o or "127.0.0.1" in o for o in settings.cors_origin_list):
            raise RuntimeError(
                "CORS_ORIGINS must be your real frontend origin(s) in production, not "
                "localhost — otherwise every state-changing request fails the CSRF check."
            )
        # Reset/verification emails build links from PUBLIC_APP_URL; a localhost
        # default in production sends users dead links.
        if "localhost" in settings.public_app_url or "127.0.0.1" in settings.public_app_url:
            raise RuntimeError(
                "PUBLIC_APP_URL must be your real frontend URL in production, not "
                "localhost — it's used to build links in reset/verification emails."
            )

    # Dev convenience: auto-create tables. Production schema is managed by Alembic
    # (`alembic upgrade head` runs on deploy — see render.yaml startCommand).
    if not settings.is_production:
        await init_models()

    # In-process job worker (E2) lives in the web process.
    await start_worker()
    try:
        yield
    finally:
        await stop_worker()


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
app.include_router(summarize.router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs", "health": "/healthz"}
