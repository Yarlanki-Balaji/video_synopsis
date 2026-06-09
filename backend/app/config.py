"""Application settings, loaded from environment / .env.

Local dev needs no config: the DB defaults to a SQLite file and email prints to
the log. Set DATABASE_URL (Aiven Postgres) and RESEND_API_KEY for real deployments.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "video-synopsis-api"
    environment: str = "development"

    # Optional infra. database_url unset -> local SQLite (see effective_database_url).
    database_url: str | None = None   # e.g. postgresql://user:pass@host:port/db
    database_ssl_ca: str | None = None  # path to a CA cert for managed PG (e.g. Aiven)
    valkey_url: str | None = None     # e.g. rediss://default:pass@host:port

    # Comma-separated list of frontend origins allowed by CORS *and* CSRF.
    cors_origins: str = "http://localhost:3000"

    # --- Google sign-in (login-only) ---
    # OAuth 2.0 "Web application" client ID (…apps.googleusercontent.com). The
    # frontend must use the SAME id (NEXT_PUBLIC_GOOGLE_CLIENT_ID). Unset -> the
    # /auth/google endpoint and the button are disabled.
    google_client_id: str | None = None

    # --- Auth / JWT ---
    # MUST be overridden in production (startup refuses the default there).
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 1440   # 24h — effective auto-logout (no client refresh)
    refresh_token_ttl_days: int = 7
    password_reset_ttl_minutes: int = 60
    # Email-verification OTP (signup).
    email_otp_ttl_minutes: int = 10
    email_otp_max_attempts: int = 5

    # Cookie behaviour. "lax" is fine when web+api share a registrable domain
    # (incl. localhost). Cross-site prod deploys need "none" + HTTPS.
    cookie_samesite: str = "lax"

    # --- Email ---
    resend_api_key: str | None = None
    email_from: str = "Video Synopsis <onboarding@resend.dev>"
    # Brevo (Sendinblue) — sends to ANY recipient after verifying a single sender
    # email (no domain needed). Set both to enable; takes priority over Resend.
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "Video Synopsis"
    public_app_url: str = "http://localhost:3000"   # used to build password-reset links

    # --- Groq / LLM (F1–F4) ---
    # No key -> a deterministic dev stub is used so the pipeline runs locally.
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    llm_max_completion_tokens: int = 3000      # shared by reasoning + 5 summaries
    llm_reasoning_effort: str = "low"          # gpt-oss-120b is a reasoning model
    llm_temperature: float = 0.3
    llm_timeout_seconds: int = 60
    # Free-tier tokens-per-minute ceiling (input + max output must fit one request).
    groq_tpm_limit: int = 8000
    llm_prompt_overhead_tokens: int = 1500     # reserve for system/instructions + JSON wrapper
    # Headroom kept BELOW the per-request ceiling so prompt boilerplate + tokenizer
    # variance can't tip a request over and trigger Groq's 413 ("request too large").
    groq_request_margin_tokens: int = 1200

    # --- Gemini (alternative summarizer; 1M-token context handles big transcripts
    # in one request, no map-reduce) ---
    # GEMINI_API_KEY may hold ONE key or a COMMA-SEPARATED list. With several keys
    # the summarizer rotates on rate/quota (429) errors — multiplying the free
    # tier's ~250 requests/day per key across all of them.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_max_output_tokens: int = 65536       # 2.5 Flash max — so long notes never truncate
    gemini_max_input_tokens: int = 900_000     # safety cap well under the 1M context
    # Summarizer backend: "auto" (Gemini if its key is set, else Groq), "gemini", "groq".
    llm_provider: str = "auto"

    @property
    def gemini_keys(self) -> list[str]:
        """All configured Gemini keys (GEMINI_API_KEY split on commas), deduped
        in order. Empty when none is set."""
        seen: dict[str, None] = {}
        for k in (self.gemini_api_key or "").split(","):
            k = k.strip()
            if k:
                seen.setdefault(k, None)
        return list(seen)

    @property
    def effective_llm_provider(self) -> str:
        choice = (self.llm_provider or "auto").lower()
        if choice == "gemini":
            return "gemini" if self.gemini_keys else "stub"
        if choice == "groq":
            return "groq" if self.groq_api_key else "stub"
        # auto
        if self.gemini_keys:
            return "gemini"
        if self.groq_api_key:
            return "groq"
        return "stub"

    # --- Beta signup cap ---
    # Max total registered users (beta). Signup is rejected once reached.
    max_users: int = 50

    # --- Quotas + circuit breaker (Postgres-authoritative, F5) ---
    # per_user_daily_jobs is the free-plan per-account daily limit.
    per_user_daily_jobs: int = 10
    global_daily_jobs: int = 50                # proxy for ~25–80 videos/day
    global_daily_tokens: int = 200_000         # Groq free TPD
    breaker_cooldown_minutes: int = 30         # after repeated Groq failures

    # --- Transcript validation floors (D5, basic) ---
    transcript_min_chars: int = 50
    # Upper bound on accepted transcript size. The map-reduce summarizer chunks
    # anything longer than one request, so this can be large; the daily token cap
    # still guards Groq cost on very long videos.
    transcript_max_chars: int = 200_000

    # --- Transcript acquisition (M3) ---
    # "local"   -> direct caption fetch (works on a residential/local IP).
    # "managed" -> call a managed transcript API (required on cloud IPs; plan §4.1).
    transcript_provider: str = "local"
    # YouTube Data API v3 key — used ONLY for video TITLE + DURATION metadata.
    # (Data API v3 cannot download caption TEXT for videos you don't own — that
    # needs OAuth as the video owner — so the transcript itself still comes from
    # the library / managed provider above; this just enriches the metadata.)
    youtube_api_key: str | None = None

    # --- Audio fallback: no captions -> download audio -> speech-to-text ---
    # Always outputs ENGLISH. Whisper first (Groq), Gemini for larger/long audio.
    # LOCAL ONLY in practice: yt-dlp is IP-blocked from cloud (same as captions).
    # ffmpeg is provided by the static-ffmpeg package (no system install needed).
    audio_fallback_enabled: bool = True
    groq_whisper_model: str = "whisper-large-v3"     # /audio/translations -> English
    groq_audio_max_bytes: int = 25 * 1024 * 1024     # Groq free-tier per-file cap
    audio_transcribe_timeout: int = 300              # seconds for the ASR request

    # --- Video/audio file upload (extract audio -> transcribe -> summarize) ---
    upload_enabled: bool = True
    max_upload_mb: int = 200                          # reject larger uploads
    upload_dir: str = ""                             # blank -> <temp>/vsai_uploads

    @property
    def upload_path(self) -> str:
        import os
        import tempfile

        return self.upload_dir or os.path.join(tempfile.gettempdir(), "vsai_uploads")

    # --- Job worker (E2–E4) ---
    job_lease_seconds: int = 180           # > worst-case single Groq call (+ repair)
    job_max_attempts: int = 3
    worker_poll_seconds: float = 1.0
    reaper_interval_seconds: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def cookie_secure(self) -> bool:
        # Only send cookies over HTTPS outside local dev.
        return self.is_production

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            url = self.database_url.strip()
            # Aiven hands out a `postgres://` URI; SQLAlchemy's async engine needs
            # the asyncpg driver. Normalize either scheme (idempotent).
            for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
                if url.startswith(prefix):
                    return "postgresql+asyncpg://" + url[len(prefix):]
            return url
        return "sqlite+aiosqlite:///./dev.db"


settings = Settings()
