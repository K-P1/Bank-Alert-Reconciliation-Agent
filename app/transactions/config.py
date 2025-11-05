"""
Transaction poller configuration.

Defines settings for polling intervals, retry policies,
API client configuration, and operational parameters.
"""

from typing import Optional
from pydantic import BaseModel, Field
from datetime import timedelta


class RetryConfig(BaseModel):
    """Configuration for retry behavior with exponential backoff."""

    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    initial_delay: float = Field(
        default=1.0, gt=0, description="Initial delay in seconds"
    )
    max_delay: float = Field(default=60.0, gt=0, description="Maximum delay in seconds")
    exponential_base: float = Field(default=2.0, gt=1, description="Backoff multiplier")
    jitter: bool = Field(
        default=True, description="Add random jitter to prevent thundering herd"
    )


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker pattern."""

    failure_threshold: int = Field(
        default=5, ge=1, description="Failures before opening circuit"
    )
    success_threshold: int = Field(
        default=2, ge=1, description="Successes to close circuit"
    )
    timeout: float = Field(
        default=60.0, gt=0, description="Seconds before attempting reset"
    )


class PollerConfig(BaseModel):
    """Main transaction poller configuration."""

    # Polling behavior
    poll_interval_minutes: int = Field(
        default=15, ge=1, description="Minutes between polling runs"
    )
    batch_size: int = Field(
        default=100, ge=1, le=1000, description="Transactions per API request"
    )
    lookback_hours: int = Field(
        default=48, ge=1, description="Hours to look back for transactions"
    )

    # API client settings
    api_client_type: str = Field(
        default="mock", description="Type of API client (mock, paystack, flutterwave)"
    )
    api_timeout: float = Field(
        default=30.0, gt=0, description="API request timeout in seconds"
    )
    api_base_url: Optional[str] = Field(
        default=None, description="Base URL for transaction API"
    )

    # Retry and resilience
    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    # Deduplication
    deduplication_enabled: bool = Field(
        default=True, description="Enable transaction deduplication"
    )
    deduplication_fields: list[str] = Field(
        default_factory=lambda: ["transaction_id", "external_source"],
        description="Fields to check for duplicates",
    )

    # Operational settings
    enabled: bool = Field(default=True, description="Enable/disable poller")
    run_on_startup: bool = Field(
        default=False, description="Run poll immediately on startup"
    )
    log_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Fraction of transactions to log in detail",
    )

    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    metrics_retention_days: int = Field(
        default=30, ge=1, description="Days to retain metrics data"
    )

    def get_poll_interval_seconds(self) -> int:
        """Get poll interval in seconds."""
        return self.poll_interval_minutes * 60

    def get_lookback_timedelta(self) -> timedelta:
        """Get lookback period as timedelta."""
        return timedelta(hours=self.lookback_hours)


# Default configuration instance
DEFAULT_POLLER_CONFIG = PollerConfig()


def get_poller_config() -> PollerConfig:
    """
    Get poller configuration from database or return defaults.

    In future versions, this will read from the config table.
    For now, returns the default configuration.
    """
    # TODO: Load from database config table
    return DEFAULT_POLLER_CONFIG
