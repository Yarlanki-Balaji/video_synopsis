# Hermes agent integration (per-user comprehension features)

Adds three personalized features on top of your existing summarizer, powered by a
**Hermes agent sidecar** (a separate service your backend calls over HTTP):

- `GET  /api/comprehension/profile` — the caller's comprehension profile
- `POST /api/comprehension/summary` — synopsis adapted to that profile
- `POST /api/comprehension/quiz` — N topic questions + 2 feedback questions
- `POST /api/comprehension/assess` — grades answers and **updates the profile**

The loop: summary → quiz → answers → assess (updates profile) → next summary adapts.

> **Already set up on this machine (this session):** Hermes sidecar running on
> `http://127.0.0.1:8642` (model `gemini-2.5-flash`, toolset `web + skills + memory`),
> `backend/.env` wired (`HERMES_ENABLED=true`), seed skills installed, frontend UI added.
> The sections below explain how to reproduce/deploy it.

## What was added to your code

| File | Change |
|---|---|
| `app/agent_client.py` | **new** — async client for the Hermes sidecar |
| `app/routers/comprehension.py` | **new** — the 4 endpoints above (JWT-protected) |
| `app/models.py` | **+`ComprehensionProfile`** — per-user adaptive memory (your DB) |
| `app/config.py` | **+`hermes_*` settings** |
| `app/main.py` | registers the new router |

Per-user state lives in **your DB** (`comprehension_profiles`), not in Hermes —
simplest and you own it. Every request is still tagged per-user, so moving to
Hermes-owned memory (Honcho) later is a config change, not a rewrite.

## 1. Run the Hermes sidecar

Install Hermes, then:

```bash
# Point Hermes at a model. You already have Gemini keys — reuse them, or use OpenRouter.
hermes model                 # pick provider + model

# LOCK DOWN the toolset (non-interactive) — a summarizer must NOT expose terminal/code/etc.
# Final api_server toolset is just: web, skills, memory.
hermes tools disable --platform api_server terminal browser code_execution delegation \
  cronjob file image_gen vision todo session_search

# Install the comprehension skills so the agent's procedure is skill-driven:
#   see ../hermes_skills/README.md  (copy the 3 skill folders into your Hermes skills dir)

# Enable its API server (in ~/.hermes/.env  — Windows: %LOCALAPPDATA%\hermes\.env)
#   API_SERVER_ENABLED=true
#   API_SERVER_KEY=<a-strong-secret>

hermes gateway               # → [API Server] listening on http://127.0.0.1:8642
```

## 2. Point your backend at it

Add to `backend/.env` (match `HERMES_API_KEY` to Hermes' `API_SERVER_KEY`):

```bash
HERMES_ENABLED=true
HERMES_BASE_URL=http://localhost:8642/v1
HERMES_API_KEY=<same-strong-secret>
HERMES_MODEL=hermes-agent
HERMES_NAMESPACE=vsai
HERMES_TIMEOUT_SECONDS=120
```

`httpx` is already a dependency. Restart your backend.

## 3. Database migrations (Alembic — wired)

Alembic is set up at `backend/alembic/` (async; `env.py` reads `DATABASE_URL` via
`app.config.settings` and targets `app.db.Base`). The initial migration
(`alembic/versions/5fe158c1939d_initial_schema.py`) creates the full schema
**including `comprehension_profiles`**. `alembic==1.18.4` is in `requirements.txt`.

- **Dev (SQLite):** `init_models()` still auto-creates tables on startup — nothing to do.
- **Fresh prod DB (Postgres):** run once on deploy (add to your release command):
  ```
  cd backend && alembic upgrade head      # DATABASE_URL must be set
  ```
  This creates the entire schema.
- **Existing prod DB that predates Alembic** (already has the old tables, just missing
  `comprehension_profiles`): mark the baseline applied, then add only the new table:
  ```
  alembic stamp head        # "the existing tables are already present"
  ```
  then create the one new table (it's the only addition):
  ```sql
  CREATE TABLE comprehension_profiles (
    user_id VARCHAR(32) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    reading_level VARCHAR(16) DEFAULT 'general',
    style_notes TEXT DEFAULT '[]',
    understanding_history TEXT DEFAULT '[]',
    updated_at TIMESTAMP
  );
  ```
- **Future model changes:** `alembic revision --autogenerate -m "..."` → review → `alembic upgrade head`.

## 4. Try it

These endpoints use the same auth as the rest of the API (access-token cookie, or
`Authorization: Bearer <token>` for the extension audience). Because of the CSRF
guard, browser calls must carry a trusted `Origin` (your frontend already does);
for a quick curl test use a Bearer token:

```bash
TOKEN=...   # an extension-audience access token

curl -X POST localhost:8000/api/comprehension/quiz \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"transcript":"<transcript text>","num_questions":5}'

curl -X POST localhost:8000/api/comprehension/assess \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"transcript":"<...>","answers":[{"question":"...","type":"comprehension","answer":"..."}]}'

curl -X POST localhost:8000/api/comprehension/summary \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"transcript":"<...>","summary_type":"detailed"}'
```

## Frontend (Next.js) — already wired
A **"Test my understanding"** button appears on completed summaries (job detail page +
workbench). It opens a modal: load quiz → answer → submit → score + per-question feedback →
**"Regenerate for my level"** (adaptive summary). Files:
- `frontend/src/lib/comprehension.ts` — typed client over `api()`
- `frontend/src/components/comprehension-quiz.tsx` — the modal state machine
- `frontend/src/components/test-understanding-button.tsx` — the trigger
Calls go through the existing `/api/*` Next.js proxy, so cookie auth + the CSRF Origin check
work without extra config.

## Deploying to production
- **DB migration:** run `cd backend && alembic upgrade head` on deploy (Alembic is wired —
  see "Database migrations" above for fresh vs. existing-DB steps).
- **Run the sidecar as its own service** (e.g. a second Render service/process): install
  `hermes-agent[web,cli]`, set `GEMINI_API_KEY` + `API_SERVER_ENABLED=true` + a strong
  `API_SERVER_KEY`, restrict the `api_server` toolset to `web, skills, memory`, install the
  skills, and start `hermes gateway`. Point the backend's `HERMES_BASE_URL` at it and share the
  secret via `HERMES_API_KEY`. Keep the sidecar private (not publicly exposed).
- **Metering:** these calls hit Gemini and bypass your job quota — add
  `quota.check_and_reserve` in the router if you want them counted.

## Optional: let Hermes create its own skills (from user answers)
Currently OFF (recommended until the feature is in real use). To enable Hermes'
self-improvement loop so it proposes new/updated skills from real usage:
- Keep the `memory` toolset on, allow skill writes, and set `skills.write_approval: true`.
- Hermes then **stages** proposed skills; review with `hermes skills` / `/skills pending` and
  approve the good ones.
- These skills are **global** (shared across users) — per-user adaptation stays in your DB.

## Notes
- If `HERMES_ENABLED=false`, the `/summary`, `/quiz`, `/assess` endpoints return
  503 (the agent is off). `/profile` still works (reads your DB).
- These endpoints are **synchronous** and bypass your job engine, quota, and the
  shared `Summary` cache — intentional, since adaptive output is per-user and can't
  use the cross-user cache. If you want quota on them, call `quota.check_and_reserve`
  inside the router (one line).
- Security: keep `HERMES_API_KEY` secret, keep Hermes bound to `127.0.0.1`, and keep
  its toolset restricted.
