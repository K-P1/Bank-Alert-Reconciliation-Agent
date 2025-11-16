"""Config model for storing system configuration and settings."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Config(Base):
    """
    Stores system configuration and settings.

    Used for runtime configuration that can be updated without code changes,
    such as matching thresholds, time windows, retention policies, etc.
    """

    __tablename__ = "config"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Configuration key-value
    key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Configuration key (e.g., 'matching.time_window_hours')",
    )
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Configuration value (stored as string, parse as needed)",
    )
    value_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="string",
        comment="Data type hint (e.g., 'string', 'int', 'float', 'bool', 'json')",
    )

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Human-readable description of this configuration"
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Configuration category (e.g., 'matching', 'email', 'retention')",
    )

    # Access control
    is_sensitive: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether this config contains sensitive data (e.g., API keys)",
    )
    is_editable: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether this config can be edited via UI/API",
    )

    # Audit
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="User or system that created this config"
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User or system that last updated this config",
    )
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

    # Indexes
    __table_args__ = (Index("idx_config_category", "category"),)

    def __repr__(self) -> str:
        return f"<Config(key={self.key}, value={self.value}, type={self.value_type})>"

    def get_typed_value(self):
        """Parse and return the value with the correct type.

        Converts the stored string value to the appropriate Python type
        based on the value_type field (int, float, bool, json, or string).

        Returns:
            The value converted to its proper type
        """
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        elif self.value_type == "json":
            import json

            return json.loads(self.value)
        else:
            return self.value
