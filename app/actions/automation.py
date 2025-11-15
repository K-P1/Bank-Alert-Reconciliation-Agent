"""Automation service for orchestrating the complete reconciliation workflow."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.unit_of_work import UnitOfWork
from app.matching.engine import MatchingEngine
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ReconciliationAutomation:
    """
    Orchestrates the complete automated reconciliation workflow.

    Coordinates:
    1. Email fetching (via EmailFetcher)
    2. Transaction polling (via TransactionPoller)
    3. Matching unprocessed emails
    4. Post-processing actions

    Runs as a background task on a configurable interval.
    """

    def __init__(
        self,
        interval_seconds: int = 900,  # 15 minutes default
        enable_actions: bool = True,
    ):
        """
        Initialize automation service.

        Args:
            interval_seconds: How often to run reconciliation (default 15 min)
            enable_actions: Whether to execute post-processing actions
        """
        self.interval_seconds = interval_seconds
        self.enable_actions = enable_actions
        self.settings = get_settings()

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stop_event = asyncio.Event()

        # Metrics
        self.total_runs = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.last_run_at: Optional[datetime] = None
        self.last_run_duration_seconds: Optional[float] = None
        self.last_run_status: Optional[str] = None
        self.last_run_stats: dict = {}

        logger.info(
            f"ReconciliationAutomation initialized "
            f"(interval: {interval_seconds}s, actions: {enable_actions})"
        )

    async def start(self):
        """Start the automation background task."""
        if self._running:
            logger.warning("[AUTOMATION] Already running, ignoring start request")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

        logger.info(
            f"[AUTOMATION] ✓ Started (interval: {self.interval_seconds}s, "
            f"actions: {'enabled' if self.enable_actions else 'disabled'})"
        )

    async def stop(self):
        """Stop the automation background task."""
        if not self._running:
            logger.warning("[AUTOMATION] Not running, ignoring stop request")
            return

        logger.info("[AUTOMATION] Stopping automation...")
        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("[AUTOMATION] Task did not stop gracefully, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("[AUTOMATION] ✓ Stopped")

    async def run_once(self) -> dict:
        """
        Run a single reconciliation cycle manually.

        Returns:
            Dictionary with run statistics
        """
        logger.info("[AUTOMATION] Manual reconciliation cycle requested")
        return await self._execute_reconciliation_cycle()

    async def _run_loop(self):
        """Main automation loop."""
        logger.info("[AUTOMATION] Background loop started")

        while self._running:
            try:
                # Execute reconciliation cycle
                await self._execute_reconciliation_cycle()

                # Wait for next cycle or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval_seconds
                    )
                    # Stop event was set, exit loop
                    break
                except asyncio.TimeoutError:
                    # Timeout reached, continue to next cycle
                    pass

            except asyncio.CancelledError:
                logger.info("[AUTOMATION] Loop cancelled")
                break
            except Exception as e:
                logger.error(
                    f"[AUTOMATION] Unexpected error in loop: {e}", exc_info=True
                )
                # Wait a bit before retrying to avoid tight error loops
                await asyncio.sleep(60)

        logger.info("[AUTOMATION] Background loop stopped")

    async def _execute_reconciliation_cycle(self) -> dict:
        """Execute a complete reconciliation cycle."""
        start_time = datetime.now(timezone.utc)
        self.total_runs += 1
        self.last_run_at = start_time

        logger.info("=" * 70)
        logger.info(f"[AUTOMATION] 🔄 Starting reconciliation cycle #{self.total_runs}")
        logger.info("=" * 70)

        stats = {
            "emails_fetched": 0,
            "transactions_polled": 0,
            "emails_matched": 0,
            "matches_successful": 0,
            "matches_needs_review": 0,
            "matches_no_candidates": 0,
            "actions_executed": 0,
            "errors": [],
        }

        try:
            # Step 1: Fetch new emails
            logger.info("[AUTOMATION] Step 1/4: Fetching new emails...")
            try:
                from app.emails.router import _fetcher

                if _fetcher:
                    # Trigger manual fetch
                    fetch_result = await _fetcher.fetch_once()
                    stats["emails_fetched"] = fetch_result.get("new_emails", 0)
                    logger.info(
                        f"[AUTOMATION] ✓ Fetched {stats['emails_fetched']} new emails"
                    )
                else:
                    logger.warning("[AUTOMATION] Email fetcher not available")
            except Exception as e:
                error_msg = f"Email fetching failed: {str(e)}"
                logger.error(f"[AUTOMATION] {error_msg}", exc_info=True)
                stats["errors"].append(error_msg)

            # Step 2: Poll transactions
            logger.info("[AUTOMATION] Step 2/4: Polling transactions...")
            try:
                from app.transactions.router import _poller

                if _poller:
                    # Trigger manual poll
                    poll_result = await _poller.poll_once()
                    stats["transactions_polled"] = poll_result.get(
                        "new_transactions", 0
                    )
                    logger.info(
                        f"[AUTOMATION] ✓ Polled {stats['transactions_polled']} new transactions"
                    )
                else:
                    logger.warning("[AUTOMATION] Transaction poller not available")
            except Exception as e:
                error_msg = f"Transaction polling failed: {str(e)}"
                logger.error(f"[AUTOMATION] {error_msg}", exc_info=True)
                stats["errors"].append(error_msg)

            # Step 3: Match unprocessed emails
            logger.info("[AUTOMATION] Step 3/4: Matching unprocessed emails...")
            try:
                from app.db.base import AsyncSessionLocal

                async with AsyncSessionLocal() as session:
                    engine = MatchingEngine(session, enable_actions=self.enable_actions)
                    batch_result = await engine.match_unmatched_emails()

                    summary = batch_result.get_summary()
                    stats["emails_matched"] = summary["total_emails"]
                    stats["matches_successful"] = summary["matched"]
                    stats["matches_needs_review"] = summary["needs_review"]
                    stats["matches_no_candidates"] = summary["no_candidates"]

                    logger.info(
                        f"[AUTOMATION] ✓ Matched {stats['emails_matched']} emails | "
                        f"Success: {stats['matches_successful']} | "
                        f"Review: {stats['matches_needs_review']} | "
                        f"No candidates: {stats['matches_no_candidates']}"
                    )

                    # Count actions executed (if enabled)
                    if self.enable_actions:
                        # Actions are executed automatically by the engine
                        # Count from audit logs
                        async with UnitOfWork() as uow:
                            recent_audits = await uow.action_audits.filter(
                                started_at__gte=start_time, limit=1000
                            )
                            stats["actions_executed"] = len(recent_audits)
                            logger.info(
                                f"[AUTOMATION] ✓ Executed {stats['actions_executed']} actions"
                            )

            except Exception as e:
                error_msg = f"Matching failed: {str(e)}"
                logger.error(f"[AUTOMATION] {error_msg}", exc_info=True)
                stats["errors"].append(error_msg)

            # Step 4: Summary
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            self.last_run_duration_seconds = duration
            self.last_run_stats = stats

            if stats["errors"]:
                self.last_run_status = "completed_with_errors"
                self.failed_runs += 1
                logger.warning(
                    f"[AUTOMATION] ⚠ Cycle completed with {len(stats['errors'])} errors"
                )
            else:
                self.last_run_status = "success"
                self.successful_runs += 1
                logger.info("[AUTOMATION] ✓ Cycle completed successfully")

            logger.info("=" * 70)
            logger.info(f"[AUTOMATION] 📊 Cycle Summary (duration: {duration:.1f}s)")
            logger.info(f"  Emails fetched: {stats['emails_fetched']}")
            logger.info(f"  Transactions polled: {stats['transactions_polled']}")
            logger.info(f"  Emails matched: {stats['emails_matched']}")
            logger.info(f"  Actions executed: {stats['actions_executed']}")
            if stats["errors"]:
                logger.info(f"  Errors: {len(stats['errors'])}")
            logger.info("=" * 70)

            return stats

        except Exception as e:
            logger.error(
                f"[AUTOMATION] Critical error in reconciliation cycle: {e}",
                exc_info=True,
            )
            self.last_run_status = "failed"
            self.failed_runs += 1
            stats["errors"].append(f"Critical error: {str(e)}")
            return stats

    def get_status(self) -> dict:
        """Get current automation status."""
        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "actions_enabled": self.enable_actions,
            "metrics": {
                "total_runs": self.total_runs,
                "successful_runs": self.successful_runs,
                "failed_runs": self.failed_runs,
                "last_run_at": (
                    self.last_run_at.isoformat() if self.last_run_at else None
                ),
                "last_run_duration_seconds": self.last_run_duration_seconds,
                "last_run_status": self.last_run_status,
                "last_run_stats": self.last_run_stats,
            },
        }


# Global instance
_automation: Optional[ReconciliationAutomation] = None


def get_automation() -> ReconciliationAutomation:
    """Get or create automation instance."""
    global _automation
    if _automation is None:
        settings = get_settings()
        # Get interval from settings or use default
        interval = getattr(settings, "AUTOMATION_INTERVAL_SECONDS", 900)
        _automation = ReconciliationAutomation(
            interval_seconds=interval, enable_actions=True
        )
    return _automation


def set_automation(automation: ReconciliationAutomation):
    """Set automation instance (for testing)."""
    global _automation
    _automation = automation
