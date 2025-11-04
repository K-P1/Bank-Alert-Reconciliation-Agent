"""Email model for storing parsed bank alert emails."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Numeric, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Email(Base):
    """
    Stores parsed email alerts from bank notifications.
    
    Each email represents a bank alert that has been fetched from IMAP
    and parsed to extract transaction-related information.
    """

    __tablename__ = "emails"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Email metadata
    message_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
        comment="Unique email message ID from IMAP"
    )
    sender: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Email sender address"
    )
    subject: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Email subject line"
    )
    body: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Full email body (HTML or plain text)"
    )

    # Parsed transaction data
    amount: Mapped[Optional[float]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True, index=True,
        comment="Parsed transaction amount"
    )
    currency: Mapped[Optional[str]] = mapped_column(
        String(3), nullable=True,
        comment="Currency code (ISO 4217, e.g., NGN, USD)"
    )
    reference: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Transaction reference or ID from email"
    )
    account_info: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Account number or masked account info"
    )

    # Timestamps
    email_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
        comment="Transaction timestamp extracted from email"
    )
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="When this email was parsed by the system"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="When this email was received (from email headers)"
    )

    # Processing metadata
    parsing_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(precision=5, scale=4), nullable=True,
        comment="Confidence score for parsing accuracy (0-1)"
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(precision=5, scale=4), nullable=True,
        comment="Alias for parsing_confidence (for compatibility)"
    )
    parsing_method: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Parsing method used (llm, regex, hybrid)"
    )
    is_processed: Mapped[bool] = mapped_column(
        default=False, nullable=False, index=True,
        comment="Whether this email has been processed for matching"
    )
    processing_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Any error encountered during processing"
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_email_amount_timestamp", "amount", "email_timestamp"),
        Index("idx_email_processed", "is_processed", "parsed_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Email(id={self.id}, message_id={self.message_id}, "
            f"amount={self.amount}, currency={self.currency})>"
        )
