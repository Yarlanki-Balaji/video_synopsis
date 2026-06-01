# Video Summarizer — Full System Design

> AI-powered video summarization web app with 6 summary types, async processing, distributed tracing, and full observability.

---

> **⚠️ Read first — this document is the SCALE TARGET (Phase 3), not the launch build.**
>
> This design assumes **self-hosted inference (Ollama + faster-whisper)** at **large scale**. The product
> is actually launching as a **real SaaS on hosted APIs at small scale (<100 users)**. For that launch,
> roughly 60% of the stack below is premature.
>
> **Beta (Phase 1) uses this committed free-tier stack instead:**
> - **LLM:** **Groq** (free tier — `llama-3.3-70b-versatile`, prompt-cache the transcript). *Drop Ollama.*
> - **Speech-to-text:** **Deepgram** — fallback only, since captions-first means ASR rarely runs.
>   *Drop faster-whisper, SymSpell/LanguageTool.*
> - **Databases:** **Aiven** managed **PostgreSQL + Valkey** (Redis-compatible), both free tier.
> - **Hosting:** **Render** free web service (FastAPI) + **Vercel** Hobby (Next.js).
> - **Async:** in-process FastAPI `BackgroundTasks` — **no separate worker** (Render workers aren't free).
>   *Defer RabbitMQ + Celery.*
> - **Scope:** **YouTube URLs only** (no object storage) · all 6 summary types generated **sequentially**.
> - **Gateway:** FastAPI middleware. *Defer Kong.*  **Observability:** Sentry + structured logs.
>   *Defer Prometheus/Grafana/Loki/Jaeger.*
> - **Add later (Phase 2, still mostly free):** AI chat (pgvector on Aiven Postgres + Groq), mind maps,
>   segmented transcript with per-section summaries, translation, custom prompt/length, file uploads (R2).
>
> Keep the sections below (RabbitMQ, Celery, Ollama, MinIO, full observability) as the documented
> "when to graduate" reference. See the validation plan for the phased build plan and rationale.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Architecture Overview](#architecture-overview)
3. [API Gateway](#api-gateway)
4. [Frontend — Next.js](#frontend--nextjs)
5. [Backend — FastAPI](#backend--fastapi)
6. [Upload → Queue → Worker → LLM Flow](#upload--queue--worker--llm-flow)
7. [Transcript Pipeline](#transcript-pipeline)
8. [LLM Summarization — 6 Types](#llm-summarization--6-types)
9. [Complete Notes Pipeline](#complete-notes-pipeline)
10. [Message Queue — RabbitMQ](#message-queue--rabbitmq)
11. [Background Workers — Celery](#background-workers--celery)
12. [Object Storage — MinIO / S3](#object-storage--minio--s3)
13. [Caching — Redis](#caching--redis)
14. [Database — PostgreSQL](#database--postgresql)
15. [Observability Stack](#observability-stack)
16. [Infrastructure Zones](#infrastructure-zones)
17. [Key Open-Source Libraries](#key-open-source-libraries)
18. [Environment Variables](#environment-variables)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js / React |
| Backend | FastAPI (Python) |
| Message Queue | RabbitMQ |
| Task Worker | Celery |
| LLM Inference | Ollama (Mistral 7B / LLaMA 3) |
| ASR (Speech-to-Text) | faster-whisper |
| Spelling Correction | SymSpell / LanguageTool |
| Cache | Redis |
| Database | PostgreSQL |
| Object Storage | MinIO (self-hosted) or AWS S3 |
| API Gateway | Kong / Nginx / Traefik |
| Monitoring | Prometheus + Grafana |
| Logging | Loki + Promtail |
| Tracing | OpenTelemetry + Jaeger |
| Auth | JWT (python-jose) + OAuth2 |

---

## Architecture Overview

```
Client (Next.js)
       │
       ▼
API Gateway  ──── Logging / Monitoring / Analytics / Tracing
       │
       ▼
FastAPI Backend  ──── Redis (cache, sessions, rate limits)
       │
       ├── Redis cache hit? → return summaries immediately
       │
       ▼
RabbitMQ (message queue)
       │
       ├── transcript.queue
       ├── summary.queue
       └── notes.queue
              │
              ▼
       Celery Workers
              │
              ├── Transcript Worker  (yt-dlp, Whisper, SymSpell)
              ├── Summary Worker     (Ollama — 6 parallel prompts)
              └── Notes Worker       (multi-pass LLM, PDF export)
              │
              ▼
       LLM Inference (Ollama)
              │
              ▼
       Results → PostgreSQL + Redis cache
              │
              ▼
       Client notified (poll /status/{job_id} or WebSocket)
```

---

## API Gateway

Sits in front of all traffic. Handles cross-cutting concerns before any request reaches FastAPI.

### Request logging

Every request and response is logged as structured JSON.

Fields captured: `method`, `path`, `status_code`, `latency_ms`, `user_id`, `ip`, `trace_id`

Logs are shipped to **Loki** (or ELK stack) for searchable, queryable log storage.

### Monitoring

Prometheus metrics exposed on `/metrics`:

- `http_request_duration_seconds` — p50, p95, p99 latency per endpoint
- `http_requests_total` — total count by status code and method
- `http_errors_total` — 4xx and 5xx breakdown

Grafana dashboards visualize these in real time.

### API analytics

Per-endpoint and per-user request tracking:

- Requests per minute by endpoint
- Top users by volume
- Rate limit counter windows stored in Redis
- Usage report data for billing or abuse detection

### Request tracking

A `trace_id` (UUID v4) is injected by the gateway into every incoming request as an HTTP header (`X-Trace-ID`). This ID is:

- Propagated through FastAPI middleware
- Attached to every Celery task message
- Logged at each worker step
- Visible end-to-end in **Jaeger** / **Zipkin** via OpenTelemetry

### Additional gateway responsibilities

- JWT validation (rejects unauthenticated requests early)
- Rate limiting (per IP and per user)
- CORS policy enforcement
- IP allowlist / blocklist
- TLS termination

---

## Frontend — Next.js

### Pages

| Route | Purpose |
|---|---|
| `/` | Landing page |
| `/login` | Auth (email + password or OAuth) |
| `/signup` | Registration |
| `/dashboard` | User history, saved summaries |
| `/summarize` | Main input page |
| `/result/[job_id]` | Summary results viewer |

### Input modes

- **YouTube URL** — paste link, backend handles download
- **File upload** — multipart chunked upload directly to object storage via presigned URL or proxied through FastAPI

### Summary type selector

Checkboxes or toggle buttons for each of the 6 types. User can select one or all. "Complete Notes" has an explicit opt-in toggle with a notice that it takes longer.

### Job status

After submission the client receives a `job_id`. It polls `GET /api/status/{job_id}` every 2 seconds (or holds a WebSocket connection) until status is `done` or `failed`.

### Auth

JWT stored in an `httpOnly` cookie. Refresh token handled server-side. No tokens in `localStorage`.

---

## Backend — FastAPI

### Key endpoints

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
DELETE /api/auth/logout

POST   /api/summarize          # submit YouTube URL or file reference
GET    /api/status/{job_id}    # poll job progress
GET    /api/result/{job_id}    # fetch completed summaries
GET    /api/history            # user's past jobs
DELETE /api/job/{job_id}       # delete a job + results

POST   /api/upload/presign     # get presigned S3/MinIO URL for direct upload
```

### Middleware stack

1. CORS
2. JWT auth (excluding public routes)
3. Request ID injection (`X-Trace-ID`)
4. OpenTelemetry span creation
5. Rate limit check (via Redis)
6. Redis cache check (for summarize endpoint)

### Task dispatch

After validating the request and writing the file reference to the database, FastAPI publishes a Celery task to RabbitMQ and returns `{job_id, status: "queued"}` to the client immediately. It does not wait for processing.

---

## Upload → Queue → Worker → LLM Flow

```
1. Client submits URL or uploads file (chunked multipart)
          │
2. FastAPI validates → saves video record to PostgreSQL
          │
3. File uploaded to MinIO / S3 (storage_path stored)
          │
4. FastAPI publishes task to RabbitMQ:
   { job_id, user_id, type: "youtube"|"upload", storage_path, summary_types[] }
          │
5. FastAPI returns { job_id, status: "queued" } to client
          │
6. Celery transcript worker picks up task
   ├── YouTube: yt-dlp + youtube-transcript-api
   └── File: extract audio → faster-whisper
          │
7. Spelling correction (SymSpell / LanguageTool)
          │
8. Clean transcript saved → Redis (TTL 12h) + PostgreSQL
          │
9. Celery summary worker picks up next task
   └── 6 parallel asyncio LLM prompts via Ollama
          │
10. Results saved → PostgreSQL + Redis (TTL 24h)
          │
11. job_status:{job_id} set to "done" in Redis
          │
12. Client poll returns results
```

### Job status values

| Status | Meaning |
|---|---|
| `queued` | Task published, not yet picked up |
| `transcribing` | Worker extracting transcript |
| `summarizing` | LLM generating summaries |
| `notes` | Notes worker running (if opted in) |
| `done` | All results ready |
| `failed` | Error occurred, message in dead-letter queue |

---

## Transcript Pipeline

```
Input
  │
  ├── YouTube URL
  │     ├── Try youtube-transcript-api (captions)
  │     │     ├── Captions found → SymSpell correction → clean transcript
  │     │     └── No captions → yt-dlp audio extract → Whisper ASR → SymSpell
  │     └── (audio file stored temporarily in MinIO, deleted after transcription)
  │
  └── Uploaded file
        └── Extract audio (ffmpeg) → faster-whisper → SymSpell → clean transcript

Chunking
  └── If transcript > 4,000 tokens:
        Split into overlapping chunks (200-token overlap)
        Each chunk processed independently
        Results merged with context headers
```

### Spelling correction

- **SymSpell** — fast dictionary-based correction for common ASR errors
- **LanguageTool API** — grammar-aware correction for sentence-level issues
- Applied after both caption and Whisper paths

---

## LLM Summarization — 6 Types

All 6 prompts are dispatched in parallel using `asyncio.gather` to the local Ollama instance.

| Type | System prompt goal | Target length |
|---|---|---|
| Brief | Concise overview a reader finishes in 1–2 min | ~200 words |
| Detailed | Comprehensive in-depth summary covering all key points | ~800 words |
| Bullet points | Unordered list of key takeaways, one idea per bullet | 10–20 bullets |
| Chapter-wise | Section breakdown using timestamps from transcript | Per chapter |
| ELI5 | Simple language, analogies, no jargon | ~300 words |
| Complete Notes | Structured study notes (see below) | Full document |

### Prompt template structure

```
System: You are an expert at summarizing video content.
        Your task: generate a {type} summary.
        Rules: {type-specific rules}
        Format: {expected output format}

User: Here is the transcript:
      {chunk_1}
      [Chunk 2 of N]
      {chunk_2}
      ...
      Generate the summary now.
```

---

## Complete Notes Pipeline

This is an opt-in, multi-pass pipeline that produces a structured document suitable for studying.

### Passes

```
Pass 1 — Structure extraction
  LLM identifies: main topics, sub-topics, section boundaries, timestamps

Pass 2 — Deep content extraction (per section)
  For each section:
    - Key concepts and definitions
    - Examples mentioned
    - Formulas, code snippets, or equations
    - Important quotes or statements

Pass 3 — Synthesis
  - Overall summary
  - Key takeaways
  - Glossary of terms
  - Further reading suggestions (if mentioned in video)
```

### Output formats

- **Markdown** (default) — copyable, renderable anywhere
- **PDF** — generated server-side via `weasyprint`
- **Structured JSON** — for downstream integrations

### Caching

Notes are cached with key `notes:{video_id}:{user_id}` (user-scoped) with TTL 48h. They are more expensive to generate than summaries, so the longer TTL reduces repeat LLM calls.

---

## Message Queue — RabbitMQ

### Queues

| Queue name | Consumer | Purpose |
|---|---|---|
| `transcript.queue` | Transcript worker | Extract and clean transcript |
| `summary.queue` | Summary worker | Generate 6 summaries |
| `notes.queue` | Notes worker | Generate complete notes |
| `dead.letter.queue` | Admin / retry handler | Failed tasks |

### Message schema

```json
{
  "job_id": "uuid",
  "user_id": "uuid",
  "task_type": "transcript | summary | notes",
  "storage_path": "s3://bucket/path/to/file.mp4",
  "youtube_url": "https://youtube.com/watch?v=...",
  "summary_types": ["brief", "detailed", "bullets", "chapters", "eli5", "notes"],
  "trace_id": "uuid",
  "created_at": "ISO8601"
}
```

### Retry policy

- Max 3 retries with exponential backoff (2s, 8s, 32s)
- On final failure: message moved to `dead.letter.queue`
- Dead letter messages trigger an alert and set job status to `failed`

---

## Background Workers — Celery

### Worker types

```
transcript_worker   — 4 replicas (CPU-bound, I/O-heavy)
summary_worker      — 2 replicas (GPU if available)
notes_worker        — 1 replica  (long-running, opt-in only)
```

### Worker lifecycle per task

```python
@celery.task(bind=True, max_retries=3)
def process_transcript(self, job_id, payload):
    update_job_status(job_id, "transcribing")
    try:
        transcript = extract_transcript(payload)
        transcript = correct_spelling(transcript)
        save_transcript(job_id, transcript)
        update_job_status(job_id, "summarizing")
        chain(process_summaries.s(job_id, transcript))()
    except Exception as exc:
        update_job_status(job_id, "failed")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### Scaling

Workers are stateless and horizontally scalable. Scale up `transcript_worker` replicas for high upload volume. Each worker connects independently to RabbitMQ and Redis.

---

## Object Storage — MinIO / S3

### Buckets

| Bucket | Contents | Retention |
|---|---|---|
| `video-uploads` | Raw uploaded video/audio files | Deleted after transcription |
| `audio-extracts` | Extracted audio from YouTube | Deleted after transcription |
| `exports` | Generated PDFs (complete notes) | 30 days |

### Upload flow

For file uploads: client requests a presigned URL from FastAPI (`POST /api/upload/presign`). The file is uploaded directly from the browser to MinIO, bypassing FastAPI. This avoids memory pressure on the app tier.

For YouTube: only the extracted audio is stored temporarily during Whisper processing.

### Access pattern

Workers access object storage directly using the `storage_path` from the task message. They stream the file rather than loading it fully into memory.

---

## Caching — Redis

### Key schema

| Key pattern | Value | TTL |
|---|---|---|
| `summary:{video_id}` | All 6 summaries (JSON) | 24h |
| `notes:{video_id}:{user_id}` | Complete notes (markdown) | 48h |
| `transcript:{video_id}` | Clean transcript text | 12h |
| `session:{user_id}` | Auth session data | JWT expiry |
| `job_status:{job_id}` | Current job status string | 1h |
| `rate_limit:{ip}` | Request count in window | 1 min |
| `rate_limit:{user_id}` | Request count in window | 1 min |

### Cache hit behaviour

When FastAPI receives a summarize request, it hashes the video URL (or file hash) to produce a `video_id` and checks Redis first. On cache hit, all summaries are returned immediately without queuing any task. This means the same YouTube video submitted by 100 users only gets processed once.

---

## Database — PostgreSQL

### Schema

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Videos
CREATE TABLE videos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(id),
    video_hash   TEXT UNIQUE,           -- SHA256 of URL or file
    source_url   TEXT,
    storage_path TEXT,
    transcript   TEXT,
    status       TEXT DEFAULT 'queued', -- queued|transcribing|summarizing|done|failed
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Summaries
CREATE TABLE summaries (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id   UUID REFERENCES videos(id),
    type       TEXT NOT NULL,           -- brief|detailed|bullets|chapters|eli5
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Complete notes
CREATE TABLE notes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id         UUID REFERENCES videos(id),
    user_id          UUID REFERENCES users(id),
    markdown_content TEXT,
    json_content     JSONB,
    pdf_path         TEXT,              -- path in object storage
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Sessions
CREATE TABLE sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id),
    refresh_token TEXT UNIQUE NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);
```

### Indexes

```sql
CREATE INDEX idx_videos_user_id    ON videos(user_id);
CREATE INDEX idx_videos_video_hash ON videos(video_hash);
CREATE INDEX idx_summaries_video   ON summaries(video_id);
CREATE INDEX idx_notes_video_user  ON notes(video_id, user_id);
```

---

## Observability Stack

### Metrics — Prometheus + Grafana

Prometheus scrapes `/metrics` from:
- API gateway (Kong or Nginx exporter)
- FastAPI (via `prometheus-fastapi-instrumentator`)
- Celery workers (via `celery-exporter`)
- RabbitMQ (via `rabbitmq_exporter`)
- Redis (via `redis_exporter`)

Key dashboards in Grafana:
- Request throughput and error rate
- Worker queue depth and processing time
- LLM inference latency per summary type
- Cache hit/miss ratio

### Logging — Loki + Promtail

Structured JSON logs from all services collected by Promtail and stored in Loki. Queryable in Grafana with LogQL.

Log fields: `timestamp`, `level`, `service`, `trace_id`, `job_id`, `user_id`, `message`

### Distributed tracing — OpenTelemetry + Jaeger

`trace_id` injected at gateway, propagated via:
- FastAPI middleware (`opentelemetry-instrumentation-fastapi`)
- Celery task headers (`opentelemetry-instrumentation-celery`)
- Database queries (`opentelemetry-instrumentation-sqlalchemy`)

Traces visualized in **Jaeger UI** — shows full span from HTTP request through queue → worker → LLM → DB write.

### Alerting

Alerts configured in Grafana Alertmanager:

| Alert | Condition |
|---|---|
| High error rate | 5xx rate > 1% for 2 min |
| Worker queue depth | Queue length > 100 for 5 min |
| Dead letter queue | Any message in DLQ |
| LLM latency | p95 > 30s |
| Disk usage | Object storage > 80% |

---

## Infrastructure Zones

```
┌──────────────────────────────────────────────────┐
│  CLIENT ZONE                                     │
│  Next.js (Vercel / self-hosted)                  │
└──────────────────────────┬───────────────────────┘
                           │ HTTPS
┌──────────────────────────▼───────────────────────┐
│  GATEWAY ZONE                                    │
│  Kong / Nginx                                    │
│  Logging · Monitoring · Analytics · Tracing      │
└──────────────────────────┬───────────────────────┘
                           │
┌──────────────────────────▼───────────────────────┐
│  APP TIER                                        │
│  FastAPI ─────────────── Redis                   │
└──────────────────────────┬───────────────────────┘
                           │ publish task
┌──────────────────────────▼───────────────────────┐
│  ASYNC TIER                                      │
│  RabbitMQ ────────────── MinIO / S3              │
│  Celery workers                                  │
└──────────────────────────┬───────────────────────┘
                           │
┌──────────────────────────▼───────────────────────┐
│  INFERENCE TIER                                  │
│  Ollama (Mistral 7B / LLaMA 3)                   │
│  faster-whisper · SymSpell                       │
│  ────────────── PostgreSQL                       │
└──────────────────────────┬───────────────────────┘
                           │ metrics / traces / logs
┌──────────────────────────▼───────────────────────┐
│  OBSERVABILITY                                   │
│  Prometheus · Grafana · Loki · Jaeger            │
└──────────────────────────────────────────────────┘
```

---

## Key Open-Source Libraries

### Backend

| Library | Purpose |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `celery[rabbitmq]` | Distributed task queue |
| `yt-dlp` | YouTube video/audio download |
| `youtube-transcript-api` | YouTube caption extraction |
| `faster-whisper` | Optimised Whisper ASR |
| `symspellpy` | Fast spelling correction |
| `ollama` | Python client for Ollama LLM |
| `sqlalchemy` | ORM |
| `alembic` | Database migrations |
| `python-jose` | JWT encode/decode |
| `passlib[bcrypt]` | Password hashing |
| `pydantic` v2 | Request/response validation |
| `redis-py` | Redis client |
| `boto3` | S3 / MinIO client |
| `weasyprint` | HTML → PDF for notes export |
| `opentelemetry-sdk` | Distributed tracing |
| `prometheus-fastapi-instrumentator` | FastAPI metrics |

### Frontend

| Library | Purpose |
|---|---|
| `next` | React framework with SSR |
| `react-query` | Server state, polling |
| `zustand` | Client state |
| `react-dropzone` | File upload UI |
| `axios` | HTTP client |

---

## Environment Variables

```env
# App
SECRET_KEY=your-jwt-secret
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/videosummarizer

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://user:pass@localhost:5672/

# Object storage
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_UPLOADS=video-uploads
S3_BUCKET_EXPORTS=exports

# LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# Whisper
WHISPER_MODEL_SIZE=base         # tiny | base | small | medium | large
WHISPER_DEVICE=cpu              # cpu | cuda

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
```

---

*Generated as part of the Video Summarizer system design. Stack: Next.js · FastAPI · RabbitMQ · Celery · Ollama · Whisper · Redis · PostgreSQL · MinIO · Kong · Prometheus · Grafana · Jaeger.*
