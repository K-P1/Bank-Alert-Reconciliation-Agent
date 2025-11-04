"""Log model for system events, errors, and audit trail."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Log(Base):
    """
    Stores system logs, events, and audit trail.
    
    Used for tracking system operations, errors, and creating an
    audit trail of all reconciliation activities.
    """

    __tablename__ = "logs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Log metadata
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="Log level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')"
    )
    event: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Event type or category (e.g., 'email_fetch', 'matching', 'api_call')"
    )
    message: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Log message"
    )

    # Context
    component: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
        comment="Component that generated the log (e.g., 'email_fetcher', 'matcher')"
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
        comment="Request ID for tracing (from x-request-id header)"
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="User ID if applicable"
    )

    # Additional details
    details: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="JSON blob with additional context"
    )
    exception: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Exception traceback if this is an error log"
    )

    # Related entities
    email_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="Related email ID if applicable"
    )
    transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="Related transaction ID if applicable"
    )
    match_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="Related match ID if applicable"
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True,
        comment="When this log entry was created"
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_log_level_timestamp", "level", "timestamp"),
        Index("idx_log_event_timestamp", "event", "timestamp"),
        Index("idx_log_component_level", "component", "level"),
    )

    def __repr__(self) -> str:
        return (
            f"<Log(id={self.id}, level={self.level}, event={self.event}, "
            f"timestamp={self.timestamp})>"
        )
