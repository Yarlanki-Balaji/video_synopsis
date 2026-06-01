# Backend — FastAPI

The summarizer API. **M1** adds auth & accounts (B1–B7): open signup (email +
password), login, JWT access tokens, rotated/hashed refresh tokens with reuse
detection, `token_version` revocation, an allowlist status checked every request,
CSRF origin checks, and password reset.

> **Deviation from the build guide:** the invite gate (B5) is removed — this is a
> private-network deployment with a known, limited set of users, so the closed-beta
> budget protection isn't needed. Signup is open; users can still be revoked.

## Run locally (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # optional; defaults work for local dev
uvicorn app.main:app --reload --port 8000
```

- Local dev uses a **SQLite** file (`dev.db`) and **console email** (reset links
  print to the server log). Set `DATABASE_URL` (Aiven Postgres) and
  `RESEND_API_KEY` for real deployments.
- http://localhost:8000/healthz · /readyz · /docs

## Sign up

Open http://localhost:3000/signup and create an account with email + password.

```powershell
# de-allowlist a user (revokes access immediately):
python -m app.cli revoke someone@example.com
```

## Auth endpoints (prefix `/auth`)

| Method & path | Purpose |
|---|---|
| `POST /auth/signup` | create account (email + password), auto-login |
| `POST /auth/login` | email + password → sets cookies |
| `POST /auth/refresh` | rotate refresh token (reuse → revoke family) |
| `POST /auth/logout` | revoke current session family + clear cookies |
| `POST /auth/logout-all` | bump `token_version` (kills all access tokens) |
| `GET  /auth/me` | current user |
| `POST /auth/request-password-reset` | always 202 (no user enumeration) |
| `POST /auth/reset-password` | consume reset token + force re-login |

State-changing browser requests must carry a trusted `Origin` (CSRF guard);
the cookies are `httpOnly`. See `app/main.py` for the CSRF middleware.

## Layout

```
backend/
  app/
    main.py            # FastAPI app, CORS, CSRF middleware, startup checks
    config.py          # env-driven settings
    db.py              # async engine/session + Valkey + Base
    models.py          # users, sessions, password_resets
    security.py        # bcrypt, token hashing, JWT mint/verify
    deps.py            # get_current_user (auth guard)
    email.py           # console (dev) / Resend (prod)
    cli.py             # revoke admin command
    routers/
      health.py        # /healthz, /readyz
      auth.py          # the auth endpoints above
  requirements.txt
  .env.example
```

> Tables are auto-created in dev via `Base.metadata.create_all`. Production will
> use Alembic migrations (added later). Times are stored as **naive UTC**.

## Not yet (deferred)

- **Rate limiting** on login / reset → M5 hardening (Valkey-backed).
- Alembic migrations + a DB-level `lower(email)` unique index for Postgres.
