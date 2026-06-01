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
- [ ] **M1 — Auth & accounts**
- [ ] **M2 — Job engine + Groq**
- [ ] **M3 — Transcript capture**
- [ ] **M4 — Frontend pages**
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

The frontend home page pings the backend `/healthz` to confirm the two talk to each
other (set `NEXT_PUBLIC_API_URL`, see `frontend/.env.local.example`).
