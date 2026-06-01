"""Application settings, loaded from environment / .env.

Everything external (Postgres, Valkey) is OPTIONAL at M0 so the app boots and
/healthz works before Aiven is provisioned. They get wired in at M2 (job ledger).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "video-synopsis-api"
    environment: str = "development"

    # Optional until Aiven is provisioned — /healthz does not depend on these.
    database_url: str | None = None   # e.g. postgresql://user:pass@host:port/db
    valkey_url: str | None = None     # e.g. rediss://default:pass@host:port

    # Comma-separated list of frontend origins allowed by CORS.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
