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
    valkey_url: str | None = None     # e.g. rediss://default:pass@host:port

    # Comma-separated list of frontend origins allowed by CORS *and* CSRF.
    cors_origins: str = "http://localhost:3000"

    # --- Auth / JWT ---
    # MUST be overridden in production (startup refuses the default there).
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 7
    password_reset_ttl_minutes: int = 60

    # Cookie behaviour. "lax" is fine when web+api share a registrable domain
    # (incl. localhost). Cross-site prod deploys need "none" + HTTPS.
    cookie_samesite: str = "lax"

    # --- Email ---
    resend_api_key: str | None = None
    email_from: str = "Video Synopsis <onboarding@resend.dev>"
    public_app_url: str = "http://localhost:3000"   # used to build password-reset links

    # --- Groq / LLM (F1–F4) ---
    # No key -> a deterministic dev stub is used so the pipeline runs locally.
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    llm_max_completion_tokens: int = 6000      # shared by reasoning + 5 summaries
    llm_reasoning_effort: str = "low"          # gpt-oss-120b is a reasoning model
    llm_temperature: float = 0.3
    llm_timeout_seconds: int = 60

    # --- Quotas + circuit breaker (Postgres-authoritative, F5) ---
    per_user_daily_jobs: int = 10
    global_daily_jobs: int = 50                # proxy for ~25–80 videos/day
    global_daily_tokens: int = 200_000         # Groq free TPD
    breaker_cooldown_minutes: int = 30         # after repeated Groq failures

    # --- Transcript validation floors (D5, basic) ---
    transcript_min_chars: int = 50
    transcript_max_chars: int = 100_000

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
            url = self.database_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return "sqlite+aiosqlite:///./dev.db"


settings = Settings()
