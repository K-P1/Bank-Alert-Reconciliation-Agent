"""Transaction model for storing polled transactions from external APIs."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Numeric, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    """
    Stores transactions fetched from external banking or payment APIs.

    These transactions are polled periodically and used as the baseline
    for matching against incoming bank alert emails.
    """

    __tablename__ = "transactions"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Transaction identification
    transaction_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique transaction ID from external system",
    )
    external_source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Source system (e.g., 'paystack', 'flutterwave', 'manual')",
    )

    # Transaction details
    amount: Mapped[float] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        index=True,
        comment="Transaction amount",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="NGN", comment="Currency code (ISO 4217)"
    )
    transaction_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Type of transaction (e.g., 'credit', 'debit', 'transfer')",
    )

    # Transaction metadata
    account_ref: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Account reference or identifier",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Transaction description or narration"
    )
    reference: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True, comment="Transaction reference code"
    )
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Customer or sender name"
    )
    customer_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Customer email address"
    )

    # Timestamps
    transaction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When the transaction occurred",
    )
    polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this transaction was fetched by the poller",
    )

    # Status and verification
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Transaction status (e.g., 'pending', 'verified', 'failed')",
    )
    is_verified: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
        comment="Whether this transaction has been verified via email match",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this transaction was verified",
    )

    # Raw data (for debugging and reprocessing)
    raw_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="JSON blob of raw API response"
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_transaction_amount_timestamp", "amount", "transaction_timestamp"),
        Index("idx_transaction_verified", "is_verified", "status"),
        Index("idx_transaction_source_status", "external_source", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.id}, transaction_id={self.transaction_id}, "
            f"amount={self.amount}, currency={self.currency}, status={self.status})>"
        )
