"""All configuration comes from environment variables (or backend/.env).

Nothing secret has a default here. See .env.example for every setting.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
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
    max_protected_images_per_account: int = 100

    # Match thresholds (section 13.12). Suggestions for human review only.
    phash_high_distance: int = 6  # Hamming distance out of 64 bits
    phash_possible_distance: int = 12
    # Embedding (CLIP) alone never makes a "high" match - see compare.py.
    cosine_high: float = 0.95  # lifts a near pHash (<= possible) to "high"
    cosine_possible: float = 0.92  # alone: at most "possible"

    # Embedding models the server accepts (must match the browser's model).
    allowed_embedding_models: list[str] = ["clip-vit-base-patch32-q8"]
    embedding_dims: int = 512

    # Discovery (phase 4)
    discovery_max_page_bytes: int = 2_000_000
    discovery_max_image_bytes: int = 15_000_000
    discovery_jobs_per_hour: int = 20
    # Lets discovery fetch localhost/private addresses. ONLY for local testing;
    # refused in production (it would open an SSRF hole).
    discovery_allow_private_hosts: bool = False
    # Run queued jobs in a background thread of the API process (handy in
    # development). In production run `python -m app.discovery.worker` instead.
    inline_worker: bool = True

    # AI agents (phase 5, section 17; provider switched to Gemini, D25).
    # "gemini" uses Google Gemini when a key is set (otherwise templates);
    # "none" never calls a model.
    llm_provider: Literal["none", "gemini"] = "gemini"
    # Read from NIVRA_GEMINI_API_KEY, or plain GEMINI_API_KEY.
    gemini_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("NIVRA_GEMINI_API_KEY", "GEMINI_API_KEY"))
    llm_model: str = "gemini-3.1-flash-lite"
    # Where paused agent runs (awaiting approval) are saved.
    agent_checkpoint_path: str = "./nivra-agents.db"
    # Where agents run: in this backend ("local") or on Maritime (optional).
    agent_runtime: Literal["local", "maritime"] = "local"
    maritime_api_key: str | None = None
    maritime_agent_id: str | None = None
    maritime_base_url: str = "https://api.maritime.sh"

    # Shared platform directory (section 18.3).
    platforms_file: str = str(Path(__file__).resolve().parents[3] / "shared" / "platforms.json")

    # Evidence locker (section 18.6). Files are encrypted in the browser; the
    # server only ever stores ciphertext it cannot read.
    evidence_dir: str = "./evidence-store"
    evidence_max_item_bytes: int = 10_000_000  # ciphertext, ~7 MB original
    evidence_quota_bytes: int = 200_000_000  # per account

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
        if settings.discovery_allow_private_hosts:
            raise RuntimeError("NIVRA_DISCOVERY_ALLOW_PRIVATE_HOSTS must be false in production")
        if settings.database_url.startswith("sqlite"):
            raise RuntimeError("Use PostgreSQL in production (D15)")
    return settings
