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
    invite_ttl_hours: int = 72
    password_reset_ttl_minutes: int = 60

    # Cookie behaviour. "lax" is fine when web+api share a registrable domain
    # (incl. localhost). Cross-site prod deploys need "none" + HTTPS.
    cookie_samesite: str = "lax"

    # --- Email ---
    resend_api_key: str | None = None
    email_from: str = "Video Synopsis <onboarding@resend.dev>"
    public_app_url: str = "http://localhost:3000"   # used to build invite/reset links

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
