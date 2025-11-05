"""
Retry and circuit breaker utilities for resilient API calls.

Implements exponential backoff with jitter and circuit breaker pattern
to handle transient failures gracefully.
"""

import asyncio
import random
from typing import Callable, TypeVar, Any, Optional, Awaitable
from datetime import datetime, timezone
from enum import Enum
import structlog

from app.transactions.config import RetryConfig, CircuitBreakerConfig

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascading failures by opening the circuit after
    a threshold of failures and periodically testing recovery.
    """

    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change: datetime = datetime.now(timezone.utc)

    def call(self, func: Callable[[], T]) -> T:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Synchronous function to execute

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
            Exception: Original exception from function
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN. "
                    f"Last failure: {self.last_failure_time}"
                )

        try:
            result = func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    async def call_async(self, func: Callable[[], Awaitable[T]]) -> T:
        """
        Execute an async function with circuit breaker protection.

        Args:
            func: Async function to execute

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
            Exception: Original exception from function
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN. "
                    f"Last failure: {self.last_failure_time}"
                )

        try:
            result = await func()
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
                logger.info(
                    "circuit_breaker_closed",
                    success_count=self.success_count,
                )

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        self.success_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
            logger.warning(
                "circuit_breaker_opened_from_half_open",
                failure_count=self.failure_count,
            )
        elif self.failure_count >= self.config.failure_threshold:
            self._transition_to_open()
            logger.warning(
                "circuit_breaker_opened",
                failure_count=self.failure_count,
                threshold=self.config.failure_threshold,
            )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True

        time_since_failure = (
            datetime.now(timezone.utc) - self.last_failure_time
        ).total_seconds()
        return time_since_failure >= self.config.timeout

    def _transition_to_open(self):
        """Transition to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_state_change = datetime.now(timezone.utc)

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.last_state_change = datetime.now(timezone.utc)
        logger.info("circuit_breaker_half_open", attempting_recovery=True)

    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = datetime.now(timezone.utc)

    def get_state(self) -> dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": (
                self.last_failure_time.isoformat() if self.last_failure_time else None
            ),
            "last_state_change": self.last_state_change.isoformat(),
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    config: RetryConfig,
    operation_name: str = "operation",
) -> T:
    """
    Execute a function with exponential backoff retry.

    Args:
        func: Async function to execute
        config: Retry configuration
        operation_name: Name for logging

    Returns:
        Function result

    Raises:
        Exception: Last exception if all retries exhausted
    """
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            coro = func()
            return await coro
        except Exception as e:
            last_exception = e
            attempt_num = attempt + 1

            if attempt_num >= config.max_attempts:
                logger.error(
                    "retry_exhausted",
                    operation=operation_name,
                    attempts=attempt_num,
                    error=str(e),
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(
                config.initial_delay * (config.exponential_base**attempt),
                config.max_delay,
            )

            # Add jitter if enabled
            if config.jitter:
                delay = delay * (0.5 + random.random() * 0.5)

            logger.warning(
                "retry_attempt",
                operation=operation_name,
                attempt=attempt_num,
                max_attempts=config.max_attempts,
                delay_seconds=delay,
                error=str(e),
            )

            await asyncio.sleep(delay)

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed without exception")
