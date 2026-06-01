# Backend — FastAPI

The summarizer API. **M1** adds auth & accounts (B1–B7): invite-gated signup,
login, JWT access tokens, rotated/hashed refresh tokens with reuse detection,
`token_version` revocation, an allowlist checked every request, CSRF origin
checks, and password reset.

## Run locally (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # optional; defaults work for local dev
uvicorn app.main:app --reload --port 8000
```

- Local dev uses a **SQLite** file (`dev.db`) and **console email** (invite/reset
  links print to the server log). Set `DATABASE_URL` (Aiven Postgres) and
  `RESEND_API_KEY` for real deployments.
- http://localhost:8000/healthz · /readyz · /docs

## Invite a tester, then sign up

```powershell
# prints an invite token + a /signup?email=...&invite=... link (also "emails" it)
python -m app.cli invite someone@example.com

# de-allowlist a user (revokes access immediately):
python -m app.cli revoke someone@example.com
```

## Auth endpoints (prefix `/auth`)

| Method & path | Purpose |
|---|---|
| `POST /auth/signup` | redeem invite + create account, auto-login |
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
    models.py          # users, invites, sessions, password_resets
    security.py        # bcrypt, token hashing, JWT mint/verify
    deps.py            # get_current_user (auth guard)
    email.py           # console (dev) / Resend (prod)
    cli.py             # invite / revoke admin commands
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
