"""Action audit log model for tracking post-processing actions."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    String,
    Text,
    DateTime,
    Numeric,
    Integer,
    ForeignKey,
    Index,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActionAudit(Base):
    """
    Audit log for all post-processing actions taken on matches.

    Records every action (verification, notification, ticket creation, etc.)
    with full context and outcome for compliance and debugging.
    """

    __tablename__ = "action_audits"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Action identification
    action_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique identifier for this action",
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of action (e.g., 'mark_verified', 'create_ticket')",
    )

    # Related entities
    match_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the match record",
    )
    email_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the email record",
    )
    transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Reference to the transaction record (if applicable)",
    )

    # Action context
    match_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Match status at time of action",
    )
    match_confidence: Mapped[float] = mapped_column(
        Numeric(precision=5, scale=4),
        nullable=False,
        comment="Match confidence at time of action",
    )
    match_outcome: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Match outcome category (matched, ambiguous, unmatched, review)",
    )

    # Execution details
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Action execution status (pending, success, failed, etc.)",
    )
    outcome: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Brief outcome description",
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed message or error description",
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if action failed",
    )

    # Metadata
    action_metadata: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON blob with action-specific metadata",
    )
    action_payload: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON blob with action payload (e.g., webhook body, ticket details)",
    )

    # Actor (who/what triggered the action)
    actor: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="system",
        index=True,
        comment="Actor that triggered the action (system, user ID, service name)",
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="When action execution started",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When action execution completed",
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Action execution duration in milliseconds",
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts",
    )
    is_retried: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this action was retried",
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
        Index("idx_action_audit_match", "match_id", "action_type"),
        Index("idx_action_audit_status", "status", "started_at"),
        Index("idx_action_audit_outcome", "match_outcome", "action_type"),
        Index("idx_action_audit_actor", "actor", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActionAudit(id={self.id}, action_id={self.action_id}, "
            f"action_type={self.action_type}, status={self.status})>"
        )
