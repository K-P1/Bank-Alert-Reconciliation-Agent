"""
Transaction poller service.

Periodically fetches transactions from external APIs and stores them
in the database with deduplication and comprehensive error handling.
"""

import asyncio
import json
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import structlog

from app.transactions.config import PollerConfig, get_poller_config
from app.transactions.clients.base import BaseTransactionClient, APIError, RawTransaction
from app.transactions.clients.mock_client import MockTransactionClient
from app.transactions.metrics import PollerMetrics, PollStatus
from app.transactions.retry import CircuitBreaker, retry_with_backoff, CircuitOpenError
from app.db.unit_of_work import UnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class TransactionPoller:
    """
    Main transaction polling service.

    Fetches transactions on a configurable interval, deduplicates,
    and stores them with comprehensive metrics and error handling.
    """

    def __init__(
        self,
        client: Optional[BaseTransactionClient] = None,
        config: Optional[PollerConfig] = None,
        session: Optional[AsyncSession] = None,
    ):
        """
        Initialize the poller.

        Args:
            client: Transaction API client (defaults to MockTransactionClient)
            config: Poller configuration (defaults to loaded config)
            session: Optional database session for testing
        """
        self.config = config or get_poller_config()
        self.client = client or self._create_default_client()
        self.metrics = PollerMetrics()
        self.circuit_breaker = CircuitBreaker(self.config.circuit_breaker)
        self._session = session

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_poll_time: Optional[datetime] = None

        logger.info(
            "poller_initialized",
            client_type=self.client.get_source_name(),
            poll_interval_minutes=self.config.poll_interval_minutes,
            lookback_hours=self.config.lookback_hours,
        )

    def _create_default_client(self) -> BaseTransactionClient:
        """Create default API client based on config."""
        if self.config.api_client_type == "mock":
            return MockTransactionClient(
                base_url=self.config.api_base_url,
                timeout=self.config.api_timeout,
            )
        # Add other client types here (Paystack, Flutterwave, etc.)
        else:
            logger.warning(
                "unknown_client_type",
                type=self.config.api_client_type,
                falling_back="mock",
            )
            return MockTransactionClient()

    async def start(self):
        """
        Start the polling loop.

        Runs in the background on configured interval.
        """
        if self._running:
            logger.warning("poller_already_running")
            return

        self._running = True
        logger.info("poller_started", interval_minutes=self.config.poll_interval_minutes)

        # Run immediately on startup if configured
        if self.config.run_on_startup:
            await self.poll_once()

        # Start the polling loop
        self._task = asyncio.create_task(self._polling_loop())

    async def stop(self):
        """Stop the polling loop gracefully."""
        if not self._running:
            return

        self._running = False
        logger.info("poller_stopping")

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("poller_stopped")

    async def _polling_loop(self):
        """Main polling loop that runs on interval."""
        while self._running:
            try:
                # Wait for next poll interval
                await asyncio.sleep(self.config.get_poll_interval_seconds())

                # Run poll
                if self.config.enabled:
                    await self.poll_once()
                else:
                    logger.debug("poller_disabled_skipping")

            except asyncio.CancelledError:
                logger.info("polling_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "polling_loop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Continue polling even after errors
                await asyncio.sleep(60)  # Wait a bit before retrying

    async def poll_once(self) -> Dict[str, Any]:
        """
        Execute a single polling run.

        Returns:
            Dictionary with poll results and metrics
        """
        run_id = self.metrics.start_run(
            source=self.client.get_source_name(),
            lookback_hours=self.config.lookback_hours,
        )

        logger.info(
            "poll_started",
            run_id=run_id,
            source=self.client.get_source_name(),
            lookback_hours=self.config.lookback_hours,
        )

        try:
            # Calculate time range
            end_time = datetime.now(timezone.utc)
            start_time = end_time - self.config.get_lookback_timedelta()

            # Fetch transactions with retry and circuit breaker
            transactions = await self._fetch_transactions_with_resilience(
                start_time, end_time
            )

            # Store transactions with deduplication
            stored_result = await self._store_transactions(transactions)

            # Update metrics
            self.metrics.record_transactions(
                fetched=len(transactions),
                new=stored_result["new"],
                duplicate=stored_result["duplicate"],
                stored=stored_result["stored"],
                failed=stored_result["failed"],
            )

            # Determine final status
            if stored_result["failed"] > 0:
                status = PollStatus.PARTIAL
            else:
                status = PollStatus.SUCCESS

            self.metrics.end_run(status)
            self._last_poll_time = datetime.now(timezone.utc)

            last_run = self.metrics.get_last_run()
            result = {
                "run_id": run_id,
                "status": status.value,
                "transactions_fetched": len(transactions),
                "transactions_new": stored_result["new"],
                "transactions_duplicate": stored_result["duplicate"],
                "transactions_stored": stored_result["stored"],
                "transactions_failed": stored_result["failed"],
                "duration_seconds": last_run.duration_seconds if last_run else 0,
            }

            logger.info("poll_completed", **result)
            return result

        except CircuitOpenError as e:
            logger.error("poll_failed_circuit_open", run_id=run_id, error=str(e))
            self.metrics.record_error(str(e))
            self.metrics.end_run(PollStatus.FAILED)
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "Circuit breaker is open",
            }

        except Exception as e:
            logger.error(
                "poll_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            self.metrics.record_error(str(e))
            self.metrics.end_run(PollStatus.FAILED)
            return {"run_id": run_id, "status": "failed", "error": str(e)}

    async def _fetch_transactions_with_resilience(
        self, start_time: datetime, end_time: datetime
    ) -> List[Any]:
        """
        Fetch transactions with retry and circuit breaker.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of raw transactions
        """

        async def fetch():
            api_start = time.time()
            try:
                transactions = await self.client.fetch_transactions(
                    start_time=start_time,
                    end_time=end_time,
                    limit=self.config.batch_size,
                )
                api_latency = time.time() - api_start
                self.metrics.record_api_call(api_latency)
                return transactions
            except Exception as e:
                api_latency = time.time() - api_start
                self.metrics.record_api_call(api_latency)
                raise

        # Wrap with circuit breaker and retry
        async def fetch_with_retry() -> List[RawTransaction]:
            return await retry_with_backoff(
                fetch, self.config.retry, operation_name="fetch_transactions"
            )
        
        return await self.circuit_breaker.call_async(fetch_with_retry)

    async def _store_transactions(
        self, raw_transactions: List[Any]
    ) -> Dict[str, int]:
        """
        Store transactions in database with deduplication.

        Args:
            raw_transactions: List of raw transaction objects

        Returns:
            Dictionary with counts: new, duplicate, stored, failed
        """
        db_start = time.time()
        result = {"new": 0, "duplicate": 0, "stored": 0, "failed": 0}

        if not raw_transactions:
            return result

        async with UnitOfWork(session=self._session) as uow:
            for raw_tx in raw_transactions:
                try:
                    # Normalize transaction data
                    tx_data = self.client.normalize_transaction(raw_tx)

                    # Check for duplicates
                    if self.config.deduplication_enabled:
                        existing = await uow.transactions.get_by_transaction_id(
                            tx_data["transaction_id"]
                        )
                        if existing:
                            result["duplicate"] += 1
                            continue

                    # Store new transaction
                    await uow.transactions.create(**tx_data)
                    result["new"] += 1
                    result["stored"] += 1

                except Exception as e:
                    logger.error(
                        "store_transaction_failed",
                        transaction_id=raw_tx.transaction_id,
                        error=str(e),
                    )
                    result["failed"] += 1
                    self.metrics.record_error(f"Store failed: {str(e)}")

            # Commit if UnitOfWork owns the session (not in test mode)
            if uow._owned_session:
                await uow.commit()

        db_latency = time.time() - db_start
        self.metrics.record_db_latency(db_latency)

        return result

    def get_status(self) -> Dict[str, Any]:
        """
        Get current poller status and metrics.

        Returns:
            Status dictionary
        """
        current_run = self.metrics.get_current_run()
        last_run = self.metrics.get_last_run()
        aggregate = self.metrics.get_aggregate_metrics(hours=24)

        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "last_poll_time": (
                self._last_poll_time.isoformat() if self._last_poll_time else None
            ),
            "circuit_breaker": self.circuit_breaker.get_state(),
            "current_run": current_run.to_dict() if current_run else None,
            "last_run": last_run.to_dict() if last_run else None,
            "metrics_24h": aggregate.to_dict(),
            "success_rate_24h": self.metrics.get_success_rate(hours=24),
            "config": {
                "poll_interval_minutes": self.config.poll_interval_minutes,
                "lookback_hours": self.config.lookback_hours,
                "batch_size": self.config.batch_size,
                "source": self.client.get_source_name(),
            },
        }

    def get_metrics(self, hours: Optional[int] = None) -> Dict[str, Any]:
        """
        Get aggregate metrics.

        Args:
            hours: Limit to last N hours (None = all history)

        Returns:
            Metrics dictionary
        """
        aggregate = self.metrics.get_aggregate_metrics(hours)
        return {
            "aggregate": aggregate.to_dict(),
            "success_rate": self.metrics.get_success_rate(hours),
            "recent_runs": [r.to_dict() for r in self.metrics.get_history(limit=10)],
        }


# Global poller instance
_poller_instance: Optional[TransactionPoller] = None


def get_poller() -> TransactionPoller:
    """
    Get or create the global poller instance.

    Returns:
        TransactionPoller singleton
    """
    global _poller_instance
    if _poller_instance is None:
        _poller_instance = TransactionPoller()
    return _poller_instance
