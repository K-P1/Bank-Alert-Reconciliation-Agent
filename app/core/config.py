from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    This uses pydantic-settings so that we get type validation and defaults.
    Settings are loaded from environment variables with optional .env file override.
    """

    # App basics
    ENV: Literal["development", "staging", "production"] = "development"
    """Environment mode: affects logging, mock data, and error handling."""

    DEBUG: bool = True
    """Enable debug mode: verbose logging and development features."""

    A2A_AGENT_NAME: str = "BARA"
    """Agent name for A2A (Agent-to-Agent) JSON-RPC protocol."""

    # DB
    DATABASE_URL: Optional[str] = None
    """Database connection URL. If None, uses SQLite for development."""

    TEST_DATABASE_URL: Optional[str] = None
    """Test database URL. Separate from main DB for testing."""

    # Email / IMAP
    IMAP_HOST: Optional[str] = None
    """IMAP server hostname for email fetching."""

    IMAP_USER: Optional[str] = None
    """IMAP username/email for authentication."""

    IMAP_PASS: Optional[str] = None
    """IMAP password for authentication."""

    # LLM / Providers (placeholder for future stages)
    LLM_PROVIDER: Optional[str] = None
    """LLM provider name (e.g., 'groq', 'openai')."""

    GROQ_API_KEY: Optional[str] = None
    """API key for Groq LLM service."""

    GROQ_MODEL: Optional[str] = None
    """Model name for Groq LLM (e.g., 'llama-3.1-8b-instant')."""

    # Mock Data Configuration (Development)
    MOCK_EMAIL_COUNT: int = 10
    """Number of mock emails to generate in development mode."""

    POLLER_BATCH_SIZE: int = 100
    """Batch size for transaction polling operations."""

    # Model config
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance to avoid re-parsing .env repeatedly.

    Uses LRU cache to ensure only one Settings instance exists per process,
    improving performance and ensuring consistency.
    """
    return Settings()
