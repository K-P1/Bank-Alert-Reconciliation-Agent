"""Data models for normalized and enriched transaction data."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EnrichmentMetadata(BaseModel):
    """Metadata about enrichment process."""

    bank_code: str | None = Field(default=None, description="Standardized bank code (e.g., GTB, FBN, ACC)")
    bank_name: str | None = Field(default=None, description="Full bank name (e.g., Guaranty Trust Bank)")
    channel: str | None = Field(default=None, description="Transaction channel (e.g., USSD, Mobile App, ATM)")
    customer_id: str | None = Field(default=None, description="Extracted customer identifier")
    enriched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When enrichment occurred")
    enrichment_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in enrichment")


class NormalizedReference(BaseModel):
    """Normalized reference string data."""

    original: str = Field(..., description="Original reference string")
    cleaned: str = Field(..., description="Cleaned reference (stripped, normalized whitespace)")
    tokens: list[str] = Field(default_factory=list, description="Extracted tokens for matching")
    alphanumeric_only: str = Field(..., description="Only alphanumeric characters")
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When normalized")


class CompositeKey(BaseModel):
    """Composite key for matching transactions."""

    amount_str: str = Field(..., description="Normalized amount as string")
    currency: str = Field(..., description="ISO currency code")
    date_bucket: str = Field(..., description="Date bucket for time window (YYYY-MM-DD-HH)")
    reference_tokens: list[str] = Field(default_factory=list, description="Top reference tokens")
    account_last4: str | None = Field(default=None, description="Last 4 digits of account number")
    
    def to_string(self) -> str:
        """Generate string representation of composite key."""
        parts = [
            self.amount_str,
            self.currency,
            self.date_bucket,
            "_".join(sorted(self.reference_tokens[:3])),  # Top 3 tokens
        ]
        if self.account_last4:
            parts.append(self.account_last4)
        return "|".join(parts)


class NormalizedEmail(BaseModel):
    """Normalized and enriched email data."""

    # Original email data (from ParsedEmail)
    message_id: str = Field(..., description="Original message ID")
    sender: str = Field(..., description="Sender email")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")

    # Normalized transaction data
    amount: Decimal | None = Field(default=None, description="Normalized amount as Decimal")
    currency: str | None = Field(default=None, description="ISO 4217 currency code (e.g., NGN, USD)")
    transaction_type: Literal["credit", "debit", "unknown"] | None = Field(
        default=None, description="Transaction type"
    )
    sender_name: str | None = Field(default=None, description="Sender name")
    recipient_name: str | None = Field(default=None, description="Recipient name")
    account_number: str | None = Field(default=None, description="Account number")
    
    # Normalized reference
    reference: NormalizedReference | None = Field(default=None, description="Normalized reference data")
    
    # Normalized timestamp (UTC)
    timestamp: datetime | None = Field(default=None, description="Normalized transaction timestamp (UTC)")
    received_at: datetime = Field(..., description="When email was received (UTC)")
    
    # Enrichment data
    enrichment: EnrichmentMetadata | None = Field(default=None, description="Enrichment metadata")
    
    # Composite key for matching
    composite_key: CompositeKey | None = Field(default=None, description="Composite key for matching")
    
    # Original parsing metadata
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When email was parsed")
    parsing_method: Literal["regex", "llm", "hybrid"] = Field(..., description="Parsing method used")
    parsing_confidence: float = Field(..., ge=0.0, le=1.0, description="Original parsing confidence")
    
    # Normalization metadata
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When normalization occurred")
    normalization_quality: float = Field(default=0.0, ge=0.0, le=1.0, description="Quality of normalization")


class NormalizedTransaction(BaseModel):
    """Normalized and enriched transaction data."""

    # Original transaction data
    transaction_id: str = Field(..., description="Unique transaction ID")
    external_source: str = Field(..., description="Source system")
    
    # Normalized transaction data
    amount: Decimal = Field(..., description="Normalized amount as Decimal")
    currency: str = Field(..., description="ISO 4217 currency code")
    transaction_type: str | None = Field(default=None, description="Transaction type")
    
    # Normalized reference
    reference: NormalizedReference | None = Field(default=None, description="Normalized reference data")
    
    # Normalized account reference
    account_ref: str | None = Field(default=None, description="Account reference")
    account_last4: str | None = Field(default=None, description="Last 4 digits of account")
    
    # Normalized timestamp (UTC)
    timestamp: datetime = Field(..., description="Transaction timestamp (UTC)")
    
    # Enrichment data
    enrichment: EnrichmentMetadata | None = Field(default=None, description="Enrichment metadata")
    
    # Composite key for matching
    composite_key: CompositeKey | None = Field(default=None, description="Composite key for matching")
    
    # Normalization metadata
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When normalization occurred")
    normalization_quality: float = Field(default=0.0, ge=0.0, le=1.0, description="Quality of normalization")
    
    # Original metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When transaction was created")
    description: str | None = Field(default=None, description="Transaction description")
