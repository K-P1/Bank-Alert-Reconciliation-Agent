"""Match model linking emails to transactions with confidence scores."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Numeric, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Match(Base):
    """
    Links email alerts to transactions with confidence scores.
    
    Represents the reconciliation results: which emails matched which
    transactions, with what confidence, and using which matching rules.
    """

    __tablename__ = "matches"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    email_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True,
        comment="Reference to the email record"
    )
    transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True,
        comment="Reference to the matched transaction (null if unmatched)"
    )

    # Match results
    matched: Mapped[bool] = mapped_column(
        default=False, nullable=False, index=True,
        comment="Whether a match was found"
    )
    confidence: Mapped[float] = mapped_column(
        Numeric(precision=5, scale=4), nullable=False, default=0.0, index=True,
        comment="Match confidence score (0-1)"
    )
    match_method: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Method used for matching (e.g., 'exact', 'fuzzy', 'heuristic')"
    )

    # Match details
    match_details: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="JSON blob with detailed matching breakdown (scores per rule)"
    )
    alternative_matches: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="JSON array of other candidate matches with lower confidence"
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True,
        comment="Match status (e.g., 'pending', 'confirmed', 'rejected', 'review')"
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="User or system that reviewed this match"
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When this match was reviewed"
    )
    review_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Notes from manual review"
    )

    # Timestamps
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="When this match was created"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships (optional, for ORM convenience)
    # Uncomment if you want to navigate relationships directly
    # email: Mapped["Email"] = relationship("Email", back_populates="matches")
    # transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="matches")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_match_email_transaction", "email_id", "transaction_id"),
        Index("idx_match_confidence", "matched", "confidence"),
        Index("idx_match_status", "status", "matched_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Match(id={self.id}, email_id={self.email_id}, "
            f"transaction_id={self.transaction_id}, matched={self.matched}, "
            f"confidence={self.confidence})>"
        )
