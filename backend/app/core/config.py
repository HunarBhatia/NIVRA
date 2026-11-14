"""All configuration comes from environment variables (or backend/.env).

Nothing secret has a default here. See .env.example for every setting.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NIVRA_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # D15: SQLite for development, PostgreSQL (+pgvector) in production.
    database_url: str = "sqlite:///./nivra-dev.db"

    # Sessions
    session_cookie_name: str = "nivra_session"
    session_ttl_hours: int = 24 * 14
    cookie_secure: bool = False  # must be True in production (HTTPS only)

    # Fernet key used to encrypt optional emails at rest. If unset, the
    # optional-email feature is disabled rather than storing plaintext.
    data_key: str | None = None

    # Rate limiting for login/registration (per client IP, per process).
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60

    # Limits that protect the database from abuse.
    max_links_per_request: int = 50
    max_links_per_case: int = 200
    max_cases_per_account: int = 20

    # Prototype-only helpers (e.g. "pretend the deadline passed").
    enable_prototype_tools: bool = True

    # Origins allowed to call the API directly (the Next.js dev server proxies
    # /api, so this is only needed when the frontend runs elsewhere).
    cors_origins: list[str] = []

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        if not settings.cookie_secure:
            raise RuntimeError("NIVRA_COOKIE_SECURE must be true in production")
        if settings.enable_prototype_tools:
            raise RuntimeError("NIVRA_ENABLE_PROTOTYPE_TOOLS must be false in production")
        if settings.database_url.startswith("sqlite"):
            raise RuntimeError("Use PostgreSQL in production (D15)")
    return settings
