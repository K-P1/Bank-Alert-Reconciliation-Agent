"""Configuration for email fetcher and parser."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Import bank mappings to dynamically build sender whitelist
from app.normalization.banks import BANK_MAPPINGS


# Build sender whitelist from all bank domains
def _build_sender_whitelist() -> list[str]:
    """Build sender whitelist from all bank domains in BANK_MAPPINGS."""
    domains = []
    for bank_info in BANK_MAPPINGS.values():
        for domain in bank_info["domains"]:
            # Add both with and without @ prefix for flexibility
            if not domain.startswith("@"):
                domains.append(f"@{domain}")
            domains.append(domain)
    
    # Remove duplicates and sort
    return sorted(set(domains))


class FetcherConfig(BaseModel):
    """Configuration for IMAP email fetcher."""

    enabled: bool = Field(default=True, description="Enable email fetcher")
    poll_interval_minutes: int = Field(
        default=15, ge=1, le=1440, description="Fetch interval in minutes"
    )
    batch_size: int = Field(
        default=50, ge=1, le=500, description="Max emails per fetch"
    )
    mark_as_read: bool = Field(
        default=True, description="Mark emails as read after fetching"
    )
    start_immediately: bool = Field(
        default=False, description="Start fetching on app startup"
    )
    imap_timeout: int = Field(
        default=30, ge=5, le=120, description="IMAP connection timeout in seconds"
    )
    mock_email_count: int = Field(
        default=10, ge=1, le=100, description="Number of mock emails to generate in dev mode"
    )


class FilterConfig(BaseModel):
    """Configuration for rule-based email filtering."""

    # Sender whitelist (domains) - dynamically built from BANK_MAPPINGS
    sender_whitelist: list[str] = Field(
        default_factory=_build_sender_whitelist,
        description="List of trusted sender domains (auto-generated from BANK_MAPPINGS)",
    )

    # Subject keyword filters (must contain at least one)
    subject_keywords: list[str] = Field(
        default=[
            "ALERT",
            "Alert",
            "alert",
            "Credit",
            "Debit",
            "Transaction",
            "TRANSACTION",
            "Transfer",
            "TRANSFER",
            "Payment",
            "PAYMENT",
            "Notification",
            "NOTIFICATION",
        ],
        description="Keywords that indicate transaction alerts",
    )

    # Blacklist patterns (exclude if present)
    blacklist_patterns: list[str] = Field(
        default=[
            "Statement",
            "STATEMENT",
            "Newsletter",
            "NEWSLETTER",
            "Password",
            "PASSWORD",
            "OTP",
            "One Time Password",
            "Reset",
            "RESET",
            "Marketing",
            "MARKETING",
            "Promo",
            "PROMO",
            "Offer",
            "OFFER",
        ],
        description="Patterns that exclude emails from processing",
    )

    # Minimum body length
    min_body_length: int = Field(
        default=50, ge=10, description="Minimum body length to consider"
    )


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""

    enabled: bool = Field(default=True, description="Enable LLM-assisted parsing")
    provider: Literal["groq"] = Field(default="groq", description="LLM provider")
    model: str = Field(default="llama-3.1-8b-instant", description="Model name")
    api_key: str | None = Field(default=None, description="API key")
    timeout: int = Field(default=30, ge=5, le=120, description="API timeout in seconds")
    max_retries: int = Field(default=2, ge=0, le=5, description="Max retry attempts")

    # Classification settings
    classification_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="Temperature for classification"
    )
    classification_max_tokens: int = Field(
        default=10, ge=5, le=50, description="Max tokens for classification"
    )

    # Extraction settings
    extraction_temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Temperature for extraction"
    )
    extraction_max_tokens: int = Field(
        default=500, ge=100, le=2000, description="Max tokens for extraction"
    )


class ParserConfig(BaseModel):
    """Configuration for email parser."""

    # Confidence thresholds
    min_confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum confidence to accept"
    )
    llm_confidence_weight: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Weight for LLM confidence"
    )
    regex_confidence_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for regex confidence"
    )

    # Parsing behavior
    fallback_to_regex: bool = Field(default=True, description="Use regex if LLM fails")
    require_amount: bool = Field(default=True, description="Require amount field")
    require_timestamp: bool = Field(
        default=False, description="Require timestamp field"
    )

    # Debug mode
    debug: bool = Field(default=False, description="Enable debug logging")
    log_low_confidence: bool = Field(
        default=True, description="Log low confidence cases"
    )


class EmailConfig(BaseModel):
    """Complete email module configuration."""

    fetcher: FetcherConfig = Field(default_factory=FetcherConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)

    @classmethod
    def from_settings(cls, settings) -> EmailConfig:
        """Create EmailConfig from app settings."""
        llm_config = LLMConfig(
            enabled=settings.GROQ_API_KEY is not None,
            provider="groq",
            model=settings.GROQ_MODEL or "llama-3.1-8b-instant",
            api_key=settings.GROQ_API_KEY,
        )

        return cls(llm=llm_config)
