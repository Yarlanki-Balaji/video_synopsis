# Video Synopsis AI

An invite-only YouTube video summarizer. Paste a URL (or use the desktop extension),
pick the summaries you want, and get them back fast.

> **Planning docs:** see [`video_synopsis_final_plan.md`](video_synopsis_final_plan.md)
> (transcript-acquisition decision + full build workflow),
> [`video_summarizer_build_guide.md`](video_summarizer_build_guide.md), and
> [`video_summarizer_system_design.md`](video_summarizer_system_design.md).

## Stack

Next.js (Vercel) · FastAPI (Render) · Aiven Postgres + Valkey · Groq `gpt-oss-120b` ·
Chrome MV3 extension + hosted transcript API + paste · Sentry.

## Repo layout

```
.
├── backend/    # FastAPI API (M0: app skeleton + /healthz, /readyz)
├── frontend/   # Next.js app (App Router, TypeScript, Tailwind)
└── *.md        # planning & design docs
```

## Build status

Following the milestone plan (`video_synopsis_final_plan.md` §8):

- [x] **M0 — Scaffold:** backend + frontend skeletons, `/healthz`
- [x] **M1 — Auth & accounts:** open signup (email + password), login, JWT + rotated/hashed
  refresh tokens (reuse-detected), `token_version` revocation, CSRF, password reset;
  `/login` + `/signup` pages *(invite gate dropped — private-network deployment)*
- [x] **M2 — Job engine + Groq:** Postgres job ledger + in-process worker/reaper
  (lease + fencing + heartbeat), Groq `gpt-oss-120b` client with dev stub, content-bound
  cache, idempotency, Postgres quotas + circuit breaker; `POST /api/summarize` + `GET /api/jobs/{id}`
- [x] **M3 — Transcript capture:** paste a YouTube URL → backend fetches the transcript
  (`POST /api/transcript`) → summarize. Direct caption fetch (`youtube-transcript-api`) works
  on a residential/local IP; on a cloud IP set `TRANSCRIPT_PROVIDER=managed` and wire a managed
  transcript API (plan §3 "Wall B"). Paste-transcript remains the universal fallback.
- [x] **M4 — Frontend pages:** Summarize (URL or paste), History (search/filter/select/export/delete),
  job detail, Settings (usage + change password), landing, login/signup, forgot/reset password;
  responsive app shell, dark/light, toasts.
- [ ] **M5 — Hardening + launch**

## Run locally

**Backend** (http://localhost:8000):
```powershell
cd backend
py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (http://localhost:3000):
```powershell
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.local.example` → `frontend/.env.local` (sets `BACKEND_ORIGIN`
so the frontend proxies `/api` and `/auth` to the backend). Then open
http://localhost:3000/signup and create an account (email + password).

## Deploy

See **[DEPLOY.md](DEPLOY.md)** — Render (backend) + Vercel (frontend) + Aiven
(Postgres/Valkey). The frontend proxies API calls so auth cookies stay first-party.
