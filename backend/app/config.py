"""Application settings, loaded from environment / .env.

Local dev needs no config: the DB defaults to a SQLite file.
Set DATABASE_URL (Aiven Postgres) for real deployments.
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

    # --- Auth / JWT ---
    # MUST be overridden in production (startup refuses the default there).
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 1440   # 24h — effective auto-logout (no client refresh)
    refresh_token_ttl_days: int = 7

    # Cookie behaviour. "lax" is fine when web+api share a registrable domain
    # (incl. localhost). Cross-site prod deploys need "none" + HTTPS.
    cookie_samesite: str = "lax"

    public_app_url: str = "http://localhost:3000"

    # --- Groq / LLM ---
    # No key -> a deterministic dev stub is used so the pipeline runs locally.
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    llm_max_completion_tokens: int = 3000
    llm_reasoning_effort: str = "low"
    llm_temperature: float = 0.3
    llm_timeout_seconds: int = 60
    groq_tpm_limit: int = 8000
    llm_prompt_overhead_tokens: int = 1500
    groq_request_margin_tokens: int = 1200

    # --- Gemini (alternative summarizer; 1M-token context handles big transcripts
    # in one request, no map-reduce) ---
    # GEMINI_API_KEY may hold ONE key or a COMMA-SEPARATED list.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_max_output_tokens: int = 65536
    gemini_max_input_tokens: int = 900_000
    # Summarizer backend: "auto" (Gemini if its key is set, else Groq), "gemini", "groq".
    llm_provider: str = "auto"

    @property
    def gemini_keys(self) -> list[str]:
        """All configured Gemini keys (GEMINI_API_KEY split on commas), deduped in order."""
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

    # --- Quotas + circuit breaker ---
    per_user_daily_jobs: int = 10
    global_daily_jobs: int = 50
    global_daily_tokens: int = 200_000
    breaker_cooldown_minutes: int = 30

    # --- Transcript validation floors ---
    transcript_min_chars: int = 50
    transcript_max_chars: int = 200_000

    # --- Transcript acquisition ---
    # "local"   -> direct caption fetch (works on a residential/local IP).
    # "managed" -> call a managed transcript API (required on cloud IPs).
    transcript_provider: str = "local"
    transcript_api_key: str | None = None
    transcript_api_url: str = "https://api.supadata.ai/v1/transcript"
    transcript_api_timeout: int = 60
    youtube_api_key: str | None = None

    # --- Audio fallback: no captions -> download audio -> speech-to-text ---
    audio_fallback_enabled: bool = True
    groq_whisper_model: str = "whisper-large-v3"
    groq_audio_max_bytes: int = 25 * 1024 * 1024
    audio_transcribe_timeout: int = 300

    # --- Video/audio file upload ---
    upload_enabled: bool = True
    max_upload_mb: int = 200
    upload_dir: str = ""             # blank -> <temp>/vsai_uploads

    @property
    def upload_path(self) -> str:
        import os
        import tempfile

        return self.upload_dir or os.path.join(tempfile.gettempdir(), "vsai_uploads")

    # --- Job worker ---
    job_lease_seconds: int = 180
    job_max_attempts: int = 3
    worker_poll_seconds: float = 1.0
    reaper_interval_seconds: int = 60

    # --- Beta signup cap ---
    max_users: int = 50

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
