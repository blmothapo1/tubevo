# filepath: backend/config.py
"""
SaaS backend configuration.

Reads all settings from environment variables (via .env).
Pydantic Settings validates types, applies defaults, and exposes them as
a typed, importable singleton — no raw os.getenv() scattered around.
"""

from __future__ import annotations

import logging
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


# ── Logging (mirrors Phase 1 format) ────────────────────────────────
LOG_DIR = Path("output")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("wealth_to_the_wise.backend")


# ── Settings ─────────────────────────────────────────────────────────

class Settings(BaseSettings):
    """Centralised, validated configuration for the backend service.

    Every field maps to an env var (case-insensitive).
    Secrets are never logged or serialised into responses.
    """

    # ── App ──────────────────────────────────────────────────────────
    app_name: str = "Wealth to the Wise"
    debug: bool = False

    # ── Server ───────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── CORS ─────────────────────────────────────────────────────────
    # Comma-separated origins for the frontend.  In dev: http://localhost:3000
    cors_origins: str = "http://localhost:3000"

    # ── Rate Limiting ────────────────────────────────────────────────
    rate_limit_default: str = "60/minute"

    # ── JWT / Auth (Item 2 will fill these in) ───────────────────────
    jwt_secret_key: str = Field(default="CHANGE-ME-BEFORE-PRODUCTION", repr=False)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # ── Database (Item 4 will fill in) ───────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./wealth.db"

    # ── External APIs (carried over from Phase 1) ────────────────────
    openai_api_key: str = Field(default="", repr=False)
    pexels_api_key: str = Field(default="", repr=False)
    elevenlabs_api_key: str = Field(default="", repr=False)
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"

    # ── YouTube / Google OAuth (Phase 2 per-user) ────────────────────
    google_client_id: str = Field(default="", repr=False)
    google_client_secret: str = Field(default="", repr=False)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",           # don't crash on Phase 1 env vars we don't use
    }

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated ``cors_origins`` into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of ``Settings()``."""
    return Settings()
