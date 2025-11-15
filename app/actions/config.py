"""Configuration for post-processing actions."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class ActionsConfig(BaseSettings):
    """Configuration for actions system.

    Handles post-processing actions like notifications, webhooks, and integrations
    that execute after transaction matching.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ACTIONS_")

    # Retry configuration
    MAX_RETRIES: int = 3
    """Maximum number of retry attempts for failed actions."""

    RETRY_DELAY_SECONDS: float = 2.0
    """Initial delay between retry attempts in seconds."""

    RETRY_BACKOFF_FACTOR: float = 2.0
    """Exponential backoff multiplier for retry delays."""

    RETRY_MAX_DELAY_SECONDS: float = 60.0
    """Maximum delay between retry attempts."""

    # Webhook configuration
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    """Timeout for webhook HTTP requests in seconds."""

    WEBHOOK_URLS: dict[str, str] = {}
    """Mapping of action types to webhook URLs for notifications."""

    # Email notification configuration
    SMTP_HOST: Optional[str] = None
    """SMTP server hostname for email notifications."""

    SMTP_PORT: int = 587
    """SMTP server port (587 for TLS, 465 for SSL, 25 for plain)."""

    SMTP_USER: Optional[str] = None
    """SMTP authentication username."""

    SMTP_PASSWORD: Optional[str] = None
    """SMTP authentication password."""

    SMTP_FROM_EMAIL: Optional[str] = None
    """Email address to send notifications from."""

    SMTP_USE_TLS: bool = True
    """Whether to use TLS encryption for SMTP."""

    # Notification recipients
    OPERATIONS_EMAIL: Optional[str] = None
    """Email address for operational notifications."""

    ESCALATION_EMAIL: Optional[str] = None
    """Email address for escalated issues and alerts."""

    # Ticket system configuration
    TICKET_SYSTEM_URL: Optional[str] = None
    """Base URL for external ticket/issue tracking system."""

    TICKET_SYSTEM_API_KEY: Optional[str] = None
    """API key for ticket system authentication."""

    TICKET_SYSTEM_TYPE: str = "generic"  # generic, jira, zendesk, etc.
    """Type of ticket system (affects API integration)."""

    # CRM configuration
    CRM_API_URL: Optional[str] = None
    """Base URL for CRM system API."""

    CRM_API_KEY: Optional[str] = None
    """API key for CRM system authentication."""

    # Action execution settings
    ENABLE_ASYNC_ACTIONS: bool = True
    """Whether to execute actions asynchronously in background."""

    ACTION_TIMEOUT_SECONDS: int = 30
    """Maximum time allowed for action execution."""

    # Audit logging
    ENABLE_ACTION_AUDIT: bool = True
    """Whether to log all action executions for audit trail."""

    AUDIT_RETENTION_DAYS: int = 90
    """Number of days to retain action audit logs."""


# Singleton instance
_config: Optional[ActionsConfig] = None


def get_actions_config() -> ActionsConfig:
    """Get or create actions configuration singleton."""
    global _config
    if _config is None:
        _config = ActionsConfig()
    return _config
