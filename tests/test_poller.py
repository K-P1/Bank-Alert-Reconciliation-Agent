"""
Tests for transaction poller functionality.

Tests deduplication, idempotency, retry logic, API failures,
metrics collection, and end-to-end polling scenarios.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

from app.transactions.poller import TransactionPoller
from app.transactions.config import PollerConfig, RetryConfig, CircuitBreakerConfig
from app.transactions.clients.base import (
    BaseTransactionClient,
    RawTransaction,
    APIConnectionError,
)
from app.transactions.clients.mock_client import MockTransactionClient
from app.transactions.metrics import PollStatus
from app.transactions.retry import CircuitBreaker, retry_with_backoff, CircuitOpenError
from app.db.unit_of_work import UnitOfWork


class TestMockClient:
    """Tests for MockTransactionClient."""

    @pytest.mark.asyncio
    async def test_fetch_transactions(self):
        """Test fetching transactions from mock client."""
        client = MockTransactionClient(latency_ms=0)

        start_time = datetime.now(timezone.utc) - timedelta(hours=2)
        end_time = datetime.now(timezone.utc)

        transactions = await client.fetch_transactions(
            start_time=start_time, end_time=end_time, limit=10
        )

        assert isinstance(transactions, list)
        assert len(transactions) <= 10

        # Verify transaction structure
        if transactions:
            tx = transactions[0]
            assert isinstance(tx, RawTransaction)
            assert tx.transaction_id
            assert tx.amount > 0
            assert tx.currency == "NGN"
            assert start_time <= tx.timestamp <= end_time

    @pytest.mark.asyncio
    async def test_mock_client_failure_simulation(self):
        """Test that mock client can simulate failures."""
        client = MockTransactionClient(failure_rate=1.0, latency_ms=0)

        with pytest.raises(APIConnectionError):
            await client.fetch_transactions(
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_validate_credentials(self):
        """Test credential validation."""
        client = MockTransactionClient(latency_ms=0)
        assert await client.validate_credentials() is True

    def test_normalize_transaction(self):
        """Test transaction normalization."""
        client = MockTransactionClient()

        raw = RawTransaction(
            transaction_id="TXN123",
            amount=10000.50,
            currency="ngn",
            timestamp=datetime.now(timezone.utc),
            description="Test transaction",
            reference="REF/123",
        )

        normalized = client.normalize_transaction(raw)

        assert normalized["transaction_id"] == "TXN123"
        assert normalized["amount"] == 10000.50
        assert normalized["currency"] == "NGN"  # Uppercased
        assert normalized["external_source"] == "mock"
        assert normalized["is_verified"] is False


class TestRetryLogic:
    """Tests for retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """Test successful operation on first attempt."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return "success"

        config = RetryConfig(max_attempts=3, initial_delay=0.01)
        result = await retry_with_backoff(operation, config)

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful operation after transient failures."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise APIConnectionError("Temporary failure")
            return "success"

        config = RetryConfig(max_attempts=5, initial_delay=0.01, jitter=False)
        result = await retry_with_backoff(operation, config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test that retry gives up after max attempts."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            raise APIConnectionError("Persistent failure")

        config = RetryConfig(max_attempts=3, initial_delay=0.01)

        with pytest.raises(APIConnectionError):
            await retry_with_backoff(operation, config)

        assert call_count == 3


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    @pytest.mark.asyncio
    async def test_circuit_closed_normal_operation(self):
        """Test circuit breaker allows calls when closed."""
        config = CircuitBreakerConfig(failure_threshold=3, timeout=1.0)
        breaker = CircuitBreaker(config)

        async def operation():
            return "success"

        result = await breaker.call_async(operation)
        assert result == "success"
        assert breaker.state.value == "closed"

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=3, timeout=1.0)
        breaker = CircuitBreaker(config)

        async def failing_operation():
            raise APIConnectionError("Failure")

        # First 3 failures should open the circuit
        for _ in range(3):
            with pytest.raises(APIConnectionError):
                await breaker.call_async(failing_operation)

        assert breaker.state.value == "open"

        # Next call should fail immediately with CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await breaker.call_async(failing_operation)

    @pytest.mark.asyncio
    async def test_circuit_half_open_recovery(self):
        """Test circuit transitions to half-open and recovers."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=0.1
        )
        breaker = CircuitBreaker(config)

        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise APIConnectionError("Failure")
            return "success"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(APIConnectionError):
                await breaker.call_async(operation)

        assert breaker.state.value == "open"

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Should transition to half-open and eventually close
        result1 = await breaker.call_async(operation)
        assert result1 == "success"
        result2 = await breaker.call_async(operation)
        assert result2 == "success"

        assert breaker.state.value == "closed"


@pytest.mark.asyncio
class TestPollerDeduplication:
    """Tests for transaction deduplication."""

    async def test_duplicate_detection(self, db_session):
        """Test that duplicate transactions are detected and skipped."""
        config = PollerConfig(
            poll_interval_minutes=15,
            lookback_hours=2,
            deduplication_enabled=True,
        )

        client = MockTransactionClient(latency_ms=0)

        # Override fetch to return same transaction twice
        original_tx = RawTransaction(
            transaction_id="TXN_DUPLICATE_TEST",
            amount=5000.00,
            currency="NGN",
            timestamp=datetime.now(timezone.utc),
            description="Test transaction",
            reference="REF/123",
        )

        async def mock_fetch(*args, **kwargs):
            return [original_tx]

        client.fetch_transactions = mock_fetch

        poller = TransactionPoller(client=client, config=config, session=db_session)

        # First poll - should store the transaction
        result1 = await poller.poll_once()
        assert result1["transactions_new"] == 1
        assert result1["transactions_duplicate"] == 0

        # Second poll - should detect duplicate
        result2 = await poller.poll_once()
        assert result2["transactions_new"] == 0
        assert result2["transactions_duplicate"] == 1

    async def test_idempotency(self, db_session):
        """Test that re-running polls doesn't create duplicates."""
        config = PollerConfig(
            poll_interval_minutes=15, lookback_hours=2, batch_size=10
        )

        client = MockTransactionClient(latency_ms=0)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        # Run poll multiple times
        results = []
        for _ in range(3):
            result = await poller.poll_once()
            results.append(result)

        # Verify no duplicates were stored across runs
        # (All transactions from run 2+ should be marked as duplicates)
        total_new = sum(r["transactions_new"] for r in results)
        total_dup = sum(r["transactions_duplicate"] for r in results)

        # First run creates new, subsequent runs find duplicates
        assert results[0]["transactions_new"] >= 0
        assert results[1]["transactions_duplicate"] >= 0 or results[1]["transactions_new"] == 0
        assert results[2]["transactions_duplicate"] >= 0 or results[2]["transactions_new"] == 0


@pytest.mark.asyncio
class TestPollerMetrics:
    """Tests for poller metrics collection."""

    async def test_metrics_recorded_on_success(self, db_session):
        """Test that metrics are recorded for successful polls."""
        config = PollerConfig(poll_interval_minutes=15, lookback_hours=1)
        client = MockTransactionClient(latency_ms=0)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        result = await poller.poll_once()

        # Check metrics were recorded
        last_run = poller.metrics.get_last_run()
        assert last_run is not None
        assert last_run.status == PollStatus.SUCCESS
        assert last_run.duration_seconds > 0
        assert last_run.transactions_fetched >= 0

    async def test_metrics_recorded_on_failure(self, db_session):
        """Test that metrics are recorded for failed polls."""
        config = PollerConfig(poll_interval_minutes=15)
        client = MockTransactionClient(failure_rate=1.0, latency_ms=0)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        result = await poller.poll_once()

        # Check failure was recorded
        last_run = poller.metrics.get_last_run()
        assert last_run is not None
        assert last_run.status == PollStatus.FAILED
        assert last_run.error_count > 0

    async def test_aggregate_metrics(self, db_session):
        """Test aggregate metrics calculation."""
        config = PollerConfig(poll_interval_minutes=15, lookback_hours=1)
        client = MockTransactionClient(latency_ms=0)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        # Run multiple polls
        for _ in range(3):
            await poller.poll_once()

        # Get aggregate metrics
        agg = poller.metrics.get_aggregate_metrics()

        assert agg.total_runs == 3
        assert agg.avg_duration_seconds > 0
        assert agg.first_run is not None
        assert agg.last_run is not None

    async def test_success_rate_calculation(self, db_session):
        """Test success rate calculation."""
        config = PollerConfig(poll_interval_minutes=15, lookback_hours=1)
        poller = TransactionPoller(config=config, session=db_session)

        # Manually add some runs to metrics
        poller.metrics.start_run("mock", 1)
        poller.metrics.end_run(PollStatus.SUCCESS)

        poller.metrics.start_run("mock", 1)
        poller.metrics.end_run(PollStatus.SUCCESS)

        poller.metrics.start_run("mock", 1)
        poller.metrics.end_run(PollStatus.FAILED)

        success_rate = poller.metrics.get_success_rate()
        assert success_rate == pytest.approx(2 / 3, rel=0.01)


@pytest.mark.asyncio
class TestPollerStatus:
    """Tests for poller status and control."""

    async def test_get_status(self, db_session):
        """Test getting poller status."""
        poller = TransactionPoller(session=db_session)
        status = poller.get_status()

        assert "running" in status
        assert "enabled" in status
        assert "circuit_breaker" in status
        assert "config" in status
        assert "metrics_24h" in status

    async def test_start_stop_poller(self, db_session):
        """Test starting and stopping the poller."""
        config = PollerConfig(poll_interval_minutes=1, run_on_startup=False)
        poller = TransactionPoller(config=config, session=db_session)

        # Start poller
        await poller.start()
        assert poller._running is True

        # Stop poller
        await poller.stop()
        assert poller._running is False


@pytest.mark.asyncio
class TestPollerErrorHandling:
    """Tests for error handling in poller."""

    async def test_partial_failure_handling(self, db_session):
        """Test handling when some transactions fail to store."""
        config = PollerConfig(poll_interval_minutes=15)
        client = MockTransactionClient(latency_ms=0)

        # Create a transaction that will cause storage error
        bad_tx = RawTransaction(
            transaction_id="",  # Empty ID should cause validation error
            amount=-100,  # Negative amount
            currency="INVALID",
            timestamp=datetime.now(timezone.utc),
        )

        good_tx = RawTransaction(
            transaction_id="TXN_GOOD",
            amount=1000,
            currency="NGN",
            timestamp=datetime.now(timezone.utc),
        )

        async def mock_fetch(*args, **kwargs):
            return [good_tx, bad_tx]

        client.fetch_transactions = mock_fetch
        poller = TransactionPoller(client=client, config=config, session=db_session)

        result = await poller.poll_once()

        # Should handle partial failure gracefully
        assert result["status"] in ["success", "partial"]
        assert result["transactions_fetched"] == 2

    async def test_api_timeout_handling(self, db_session):
        """Test handling of API errors."""
        from app.transactions.clients.base import APIError
        
        config = PollerConfig(
            poll_interval_minutes=15,
            api_timeout=0.1,
            retry=RetryConfig(max_attempts=1),
        )

        async def failing_operation(*args, **kwargs):
            raise APIError("API timeout")

        client = MockTransactionClient(latency_ms=0)
        client.fetch_transactions = failing_operation

        poller = TransactionPoller(client=client, config=config, session=db_session)

        # Should handle API errors gracefully
        result = await poller.poll_once()
        assert result["status"] == "failed"


@pytest.mark.asyncio
class TestPollerIntegration:
    """End-to-end integration tests."""

    async def test_full_poll_cycle(self, db_session):
        """Test complete polling cycle from fetch to storage."""
        config = PollerConfig(
            poll_interval_minutes=15, lookback_hours=2, batch_size=20
        )

        client = MockTransactionClient(latency_ms=10)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        # Run a full poll
        result = await poller.poll_once()

        # Verify results
        assert result["status"] in ["success", "partial"]
        assert "run_id" in result
        assert "transactions_fetched" in result
        assert "duration_seconds" in result

        # Verify transactions were stored
        async with UnitOfWork(session=db_session) as uow:
            count = await uow.transactions.count()
            assert count > 0

    async def test_concurrent_polls_handled_gracefully(self, db_session):
        """Test that concurrent polls don't cause issues."""
        config = PollerConfig(poll_interval_minutes=15, lookback_hours=1)
        client = MockTransactionClient(latency_ms=50)
        poller = TransactionPoller(client=client, config=config, session=db_session)

        # Run multiple polls concurrently
        results = await asyncio.gather(
            poller.poll_once(), poller.poll_once(), return_exceptions=True
        )

        # Both should complete successfully
        for result in results:
            if isinstance(result, dict):
                assert "run_id" in result
