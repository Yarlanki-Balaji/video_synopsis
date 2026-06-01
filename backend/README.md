# Backend — FastAPI

The summarizer API. At M0 this is just the app skeleton + health endpoints.

## Run locally (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # optional; defaults work without it
uvicorn app.main:app --reload --port 8000
```

Then:
- http://localhost:8000/healthz → `{"status":"ok",...}` (liveness)
- http://localhost:8000/readyz  → reports Postgres/Valkey (`not_configured` until Aiven is wired)
- http://localhost:8000/docs    → interactive API docs

## Layout

```
backend/
  app/
    main.py            # FastAPI app + CORS, includes routers
    config.py          # env-driven settings (pydantic-settings)
    db.py              # lazy Postgres (SQLAlchemy async) + Valkey clients
    routers/
      health.py        # /healthz, /readyz
  requirements.txt
  .env.example
```

Postgres and Valkey are optional at M0 — the app boots and `/healthz` works with
no database. They get used starting at M2 (the job ledger).
