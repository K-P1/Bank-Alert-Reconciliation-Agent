"""Data models for email parsing."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class RawEmail(BaseModel):
    """Raw email data fetched from IMAP."""

    message_id: str = Field(..., description="Unique message ID")
    sender: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject")
    body_plain: str | None = Field(default=None, description="Plain text body")
    body_html: str | None = Field(default=None, description="HTML body")
    received_at: datetime = Field(..., description="When email was received")
    uid: int | None = Field(default=None, description="IMAP UID")
    flags: list[str] = Field(default_factory=list, description="IMAP flags")


class ParsedEmail(BaseModel):
    """Parsed and structured email data."""

    # Original email reference
    message_id: str = Field(..., description="Original message ID")
    sender: str = Field(..., description="Sender email")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body (plain or HTML)")

    # Extracted transaction data
    amount: Decimal | None = Field(default=None, description="Transaction amount")
    currency: str | None = Field(default=None, description="Currency code (e.g., NGN, USD)")
    transaction_type: Literal["credit", "debit", "unknown"] | None = Field(
        default=None, description="Transaction type"
    )
    sender_name: str | None = Field(default=None, description="Transaction sender name")
    recipient_name: str | None = Field(default=None, description="Transaction recipient name")
    reference: str | None = Field(default=None, description="Transaction reference number")
    account_number: str | None = Field(default=None, description="Account number")
    email_timestamp: datetime | None = Field(default=None, description="Transaction timestamp from email")

    # Metadata
    received_at: datetime = Field(..., description="When email was received")
    parsed_at: datetime = Field(default_factory=datetime.utcnow, description="When email was parsed")
    parsing_method: Literal["regex", "llm", "hybrid"] = Field(..., description="Parsing method used")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Parsing confidence score")
    is_alert: bool = Field(..., description="Whether this is a transaction alert")

    # Error tracking
    parsing_errors: list[str] = Field(default_factory=list, description="Parsing errors encountered")


class FilterResult(BaseModel):
    """Result of rule-based filtering."""

    passed: bool = Field(..., description="Whether email passed filters")
    reason: str | None = Field(default=None, description="Reason for filtering out")
    matched_whitelist: bool = Field(default=False, description="Matched sender whitelist")
    matched_keywords: list[str] = Field(default_factory=list, description="Matched keywords")
    matched_blacklist: list[str] = Field(default_factory=list, description="Matched blacklist patterns")


class LLMClassificationResult(BaseModel):
    """Result of LLM classification."""

    is_alert: bool = Field(..., description="Whether email is a transaction alert")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str | None = Field(default=None, description="LLM reasoning")
    raw_response: str | None = Field(default=None, description="Raw LLM response")


class LLMExtractionResult(BaseModel):
    """Result of LLM extraction."""

    amount: Decimal | None = Field(default=None, description="Extracted amount")
    currency: str | None = Field(default=None, description="Extracted currency")
    transaction_type: Literal["credit", "debit", "unknown"] | None = Field(default=None, description="Transaction type")
    sender_name: str | None = Field(default=None, description="Sender name")
    recipient_name: str | None = Field(default=None, description="Recipient name")
    reference: str | None = Field(default=None, description="Reference number")
    account_number: str | None = Field(default=None, description="Account number")
    timestamp: datetime | None = Field(default=None, description="Transaction timestamp")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    fields_extracted: int = Field(..., description="Number of fields successfully extracted")
    raw_response: str | None = Field(default=None, description="Raw LLM response")


class RegexExtractionResult(BaseModel):
    """Result of regex extraction."""

    amount: Decimal | None = Field(default=None, description="Extracted amount")
    currency: str | None = Field(default=None, description="Extracted currency")
    transaction_type: Literal["credit", "debit", "unknown"] | None = Field(default=None, description="Transaction type")
    sender_name: str | None = Field(default=None, description="Sender name")
    reference: str | None = Field(default=None, description="Reference number")
    account_number: str | None = Field(default=None, description="Account number")
    timestamp: datetime | None = Field(default=None, description="Transaction timestamp")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    fields_extracted: int = Field(..., description="Number of fields successfully extracted")
    patterns_matched: dict[str, str] = Field(default_factory=dict, description="Patterns that matched")
