from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    This uses pydantic-settings so that we get type validation and defaults.
    """

    # App basics
    ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    A2A_AGENT_NAME: str = "BARA"

    # DB
    DATABASE_URL: Optional[str] = None
    TEST_DATABASE_URL: Optional[str] = None

    # Email / IMAP
    IMAP_HOST: Optional[str] = None
    IMAP_USER: Optional[str] = None
    IMAP_PASS: Optional[str] = None

    # LLM / Providers (placeholder for future stages)
    LLM_PROVIDER: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: Optional[str] = None

    # Mock Data Configuration (Development)
    MOCK_EMAIL_COUNT: int = 10
    POLLER_BATCH_SIZE: int = 100

    # Model config
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance to avoid re-parsing .env repeatedly."""
    return Settings()
