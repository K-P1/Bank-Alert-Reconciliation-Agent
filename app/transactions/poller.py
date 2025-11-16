"""
Transaction poller service.

Periodically fetches transactions from external APIs and stores them
in the database with deduplication and comprehensive error handling.
"""

import asyncio
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import structlog

from app.transactions.config import PollerConfig, get_poller_config
from app.transactions.clients.base import BaseTransactionClient, RawTransaction
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
            "poller.initialized",
            client_type=self.client.get_source_name(),
            poll_interval_minutes=self.config.poll_interval_minutes,
            lookback_hours=self.config.lookback_hours,
            enabled=self.config.enabled,
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
            logger.warning("poller.already_running")
            return

        self._running = True
        logger.info(
            "poller.started",
            interval_minutes=self.config.poll_interval_minutes,
            run_on_startup=self.config.run_on_startup,
        )

        # Run immediately on startup if configured
        if self.config.run_on_startup:
            logger.info("poller.running_initial_poll")
            await self.poll_once()

        # Start the polling loop
        self._task = asyncio.create_task(self._polling_loop())

    async def stop(self):
        """Stop the polling loop gracefully."""
        if not self._running:
            logger.debug("poller.not_running")
            return

        self._running = False
        logger.info("poller.stopping")

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("poller.stopped")

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
            "poll.started",
            run_id=run_id,
            source=self.client.get_source_name(),
            lookback_hours=self.config.lookback_hours,
            batch_size=self.config.batch_size,
        )

        try:
            # Calculate time range
            end_time = datetime.now(timezone.utc)
            start_time = end_time - self.config.get_lookback_timedelta()

            logger.debug(
                "poll.time_range",
                run_id=run_id,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
            )

            # Fetch transactions with retry and circuit breaker
            logger.info("poll.fetching_transactions", run_id=run_id)
            transactions = await self._fetch_transactions_with_resilience(
                start_time, end_time
            )

            logger.info(
                "poll.transactions_fetched",
                run_id=run_id,
                count=len(transactions),
            )

            # Store transactions with deduplication
            logger.info("poll.storing_transactions", run_id=run_id)
            stored_result = await self._store_transactions(transactions)

            # Update metrics
            self.metrics.record_transactions(
                fetched=len(transactions),
                new=stored_result["new"],
                duplicate=stored_result["duplicate"],
                stored=stored_result["stored"],
                failed=stored_result["failed"],
            )

            logger.info(
                "poll.storage_complete",
                run_id=run_id,
                new=stored_result["new"],
                duplicate=stored_result["duplicate"],
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

            logger.info(
                "poll.completed",
                run_id=run_id,
                status=status.value,
                fetched=len(transactions),
                new=stored_result["new"],
                duplicate=stored_result["duplicate"],
                failed=stored_result["failed"],
                duration_seconds=result["duration_seconds"],
            )
            return result

        except CircuitOpenError as e:
            logger.error("poll.failed.circuit_open", run_id=run_id, error=str(e))
            self.metrics.record_error(str(e))
            self.metrics.end_run(PollStatus.FAILED)
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "Circuit breaker is open",
            }

        except Exception as e:
            logger.error(
                "poll.failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
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
            except Exception:
                api_latency = time.time() - api_start
                self.metrics.record_api_call(api_latency)
                raise

        # Wrap with circuit breaker and retry
        async def fetch_with_retry() -> List[RawTransaction]:
            return await retry_with_backoff(
                fetch, self.config.retry, operation_name="fetch_transactions"
            )

        return await self.circuit_breaker.call_async(fetch_with_retry)

    async def _store_transactions(self, raw_transactions: List[Any]) -> Dict[str, int]:
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

        logger.debug("storage.started", count=len(raw_transactions))

        async with UnitOfWork(session=self._session) as uow:
            for idx, raw_tx in enumerate(raw_transactions, 1):
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
                            logger.debug(
                                "storage.duplicate",
                                transaction_id=tx_data["transaction_id"],
                                idx=idx,
                            )
                            continue

                    # Store new transaction
                    await uow.transactions.create(**tx_data)
                    result["new"] += 1
                    result["stored"] += 1
                    logger.debug(
                        "storage.stored",
                        transaction_id=tx_data["transaction_id"],
                        idx=idx,
                    )

                except Exception as e:
                    logger.error(
                        "storage.failed",
                        transaction_id=getattr(raw_tx, "transaction_id", "unknown"),
                        idx=idx,
                        error=str(e),
                    )
                    result["failed"] += 1
                    self.metrics.record_error(f"Store failed: {str(e)}")

            # Always commit within UnitOfWork context
            await uow.commit()

        db_latency = time.time() - db_start
        self.metrics.record_db_latency(db_latency)

        logger.info(
            "storage.complete",
            total=len(raw_transactions),
            new=result["new"],
            duplicate=result["duplicate"],
            failed=result["failed"],
            latency_seconds=db_latency,
        )

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
            Metrics dictionary with enabled status
        """
        aggregate = self.metrics.get_aggregate_metrics(hours)
        return {
            "enabled": self.config.enabled,
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
