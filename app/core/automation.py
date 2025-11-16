"""
Unified automation service for BARA.

Orchestrates the complete reconciliation cycle:
1. Fetch emails from IMAP
2. Poll transactions from API
3. Run matching engine

Replaces the separate email fetcher and transaction poller services
with a single unified automation loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

from app.core.config import get_settings
from app.db.base import get_db
from app.emails.router import trigger_fetch
from app.transactions.router import trigger_poll
from app.matching.engine import match_unmatched

logger = structlog.get_logger("automation")


class AutomationService:
    """
    Unified automation service for orchestrating reconciliation cycles.

    Runs a continuous loop that:
    1. Fetches new emails
    2. Polls for new transactions
    3. Runs the matching engine
    """

    def __init__(self, interval_seconds: int = 300):
        """
        Initialize automation service.

        Args:
            interval_seconds: Time between automation cycles (default: 5 minutes)
        """
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._last_run: Optional[datetime] = None
        self._last_error: Optional[str] = None

        # Metrics
        self.total_cycles = 0
        self.successful_cycles = 0
        self.failed_cycles = 0

        logger.info(
            "automation.initialized",
            interval_seconds=interval_seconds,
        )

    async def start(self, interval_seconds: Optional[int] = None) -> dict:
        """
        Start the automation service.

        Args:
            interval_seconds: Override the default interval

        Returns:
            Status dictionary
        """
        if self._running:
            logger.warning("automation.already_running")
            return {
                "success": False,
                "message": "Automation is already running",
                "running": True,
            }

        if interval_seconds is not None:
            self.interval_seconds = interval_seconds

        self._running = True
        self._task = asyncio.create_task(self._automation_loop())

        logger.info(
            "automation.started",
            interval_seconds=self.interval_seconds,
        )

        return {
            "success": True,
            "message": f"Automation started (interval: {self.interval_seconds}s)",
            "running": True,
            "interval_seconds": self.interval_seconds,
        }

    async def stop(self) -> dict:
        """
        Stop the automation service.

        Returns:
            Status dictionary
        """
        if not self._running:
            logger.debug("automation.not_running")
            return {
                "success": False,
                "message": "Automation is not running",
                "running": False,
            }

        logger.info("automation.stopping")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("automation.stopped")

        return {
            "success": True,
            "message": "Automation stopped",
            "running": False,
            "total_cycles": self.total_cycles,
            "successful_cycles": self.successful_cycles,
            "failed_cycles": self.failed_cycles,
        }

    async def _automation_loop(self) -> None:
        """Main automation loop."""
        logger.info("automation.loop_started")

        while self._running:
            try:
                await self.run_cycle()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                logger.info("automation.loop_cancelled")
                break
            except Exception as exc:
                logger.exception("automation.loop_error", error=str(exc))
                self._last_error = str(exc)
                # Continue running despite errors
                await asyncio.sleep(self.interval_seconds)

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single automation cycle.

        Returns:
            Cycle statistics dictionary
        """
        cycle_start = datetime.now(timezone.utc)
        self._cycle_count += 1
        self.total_cycles += 1

        logger.info(
            "automation.cycle_start",
            cycle=self._cycle_count,
            timestamp=cycle_start.isoformat(),
        )

        stats: Dict[str, Any] = {
            "cycle": self._cycle_count,
            "started_at": cycle_start.isoformat(),
            "emails": {},
            "transactions": {},
            "matching": {},
        }

        try:
            # Step 1: Fetch emails
            logger.info("automation.cycle.step_1.fetch_emails")
            try:
                email_result = await trigger_fetch()
                if stats["emails"] is None:
                    stats["emails"] = {}
                stats["emails"] = {
                    "fetched": email_result.emails_fetched,
                    "processed": email_result.emails_processed,
                    "stored": email_result.emails_stored,
                    "error": email_result.error,
                }
                logger.info(
                    "automation.cycle.step_1.success",
                    emails_stored=email_result.emails_stored,
                )
            except Exception as exc:
                logger.error("automation.cycle.step_1.error", error=str(exc))
                if not isinstance(stats["emails"], dict):
                    stats["emails"] = {}
                stats["emails"]["error"] = str(exc)

            # Step 2: Poll transactions
            logger.info("automation.cycle.step_2.poll_transactions")
            try:
                txn_result = await trigger_poll()
                stats["transactions"] = {
                    "status": txn_result.status,
                    "message": txn_result.message,
                    "details": txn_result.details,
                }
                logger.info(
                    "automation.cycle.step_2.success",
                    status=txn_result.status,
                )
            except Exception as exc:
                logger.error("automation.cycle.step_2.error", error=str(exc))
                if not isinstance(stats["transactions"], dict):
                    stats["transactions"] = {}
                stats["transactions"]["error"] = str(exc)

            # Step 3: Run matching
            logger.info("automation.cycle.step_3.match")
            try:
                # Get database session
                async for db in get_db():
                    match_result = await match_unmatched(db, limit=None)
                    stats["matching"] = {
                        "total_emails": match_result.total_emails,
                        "total_matched": match_result.total_matched,
                        "total_needs_review": match_result.total_needs_review,
                        "total_rejected": match_result.total_rejected,
                        "total_no_candidates": match_result.total_no_candidates,
                        "average_confidence": match_result.average_confidence,
                    }
                    logger.info(
                        "automation.cycle.step_3.success",
                        matched=match_result.total_matched,
                    )
                    break  # Only need first iteration
            except Exception as exc:
                logger.error("automation.cycle.step_3.error", error=str(exc))
                if not isinstance(stats["matching"], dict):
                    stats["matching"] = {}
                stats["matching"]["error"] = str(exc)

            cycle_end = datetime.now(timezone.utc)
            duration = (cycle_end - cycle_start).total_seconds()

            stats["completed_at"] = cycle_end.isoformat()
            stats["duration_seconds"] = duration
            stats["success"] = True

            self._last_run = cycle_end
            self.successful_cycles += 1

            logger.info(
                "automation.cycle_complete",
                cycle=self._cycle_count,
                duration_seconds=duration,
            )

            return stats

        except Exception as exc:
            logger.exception("automation.cycle_failed", error=str(exc))
            self.failed_cycles += 1
            self._last_error = str(exc)
            stats["success"] = False
            stats["error"] = str(exc)
            return stats

    def get_status(self) -> dict:
        """
        Get current automation status.

        Returns:
            Status dictionary with metrics compatible with AutomationStatusResponse
        """
        # Get component status
        from app.emails.router import _fetcher as email_fetcher
        from app.transactions.poller import get_poller

        # Email fetcher status
        email_status = {
            "enabled": email_fetcher is not None,
            "running": email_fetcher._running if email_fetcher else False,
            "total_fetches": (email_fetcher.total_fetches if email_fetcher else 0),
        }

        # Transaction poller status
        poller = get_poller()
        poller_metrics = poller.metrics.get_aggregate_metrics()
        transaction_status = {
            "enabled": poller.config.enabled,
            "running": poller._running,
            "total_runs": poller_metrics.total_runs,
            "total_transactions": poller_metrics.total_transactions,
        }

        # Matching engine status
        match_status = {
            "total_matches": self.successful_cycles,  # Approximate
        }

        return {
            "running": self._running,
            "enabled": True,  # Service is always enabled (can be started/stopped)
            "interval_seconds": self.interval_seconds,
            "cycles_completed": self.total_cycles,
            "last_cycle": (
                {
                    "timestamp": self._last_run.isoformat(),
                    "success_rate": (
                        (self.successful_cycles / self.total_cycles * 100)
                        if self.total_cycles > 0
                        else 0
                    ),
                }
                if self._last_run
                else None
            ),
            "errors_count": self.failed_cycles,
            "email_fetcher": email_status,
            "transaction_poller": transaction_status,
            "match_engine": match_status,
        }

    async def run_matching(self) -> dict:
        """
        Run matching engine manually (public method for API calls).

        Returns:
            Match results dictionary
        """
        logger.info("automation.manual_match.start")

        try:
            # Get database session
            async for db in get_db():
                match_result = await match_unmatched(db, limit=None)
                result = {
                    "matches_created": match_result.total_matched,
                    "emails_matched": match_result.total_matched,
                    "total_emails": match_result.total_emails,
                    "total_matched": match_result.total_matched,
                    "total_needs_review": match_result.total_needs_review,
                    "total_rejected": match_result.total_rejected,
                    "total_no_candidates": match_result.total_no_candidates,
                    "average_confidence": match_result.average_confidence,
                }
                logger.info(
                    "automation.manual_match.success",
                    matched=match_result.total_matched,
                )
                return result

            # Fallback if no DB session
            return {
                "matches_created": 0,
                "emails_matched": 0,
                "error": "No database session available",
            }

        except Exception as exc:
            logger.error("automation.manual_match.error", error=str(exc))
            return {"matches_created": 0, "emails_matched": 0, "error": str(exc)}


# Global automation service instance
_automation_service: Optional[AutomationService] = None


def get_automation_service() -> AutomationService:
    """Get the global automation service instance."""
    global _automation_service
    if _automation_service is None:
        settings = get_settings()
        # Default to 5 minutes (300 seconds)
        interval = getattr(settings, "AUTOMATION_INTERVAL_SECONDS", 300)
        _automation_service = AutomationService(interval_seconds=interval)
    return _automation_service


def set_automation_service(service: AutomationService) -> None:
    """Set the global automation service instance."""
    global _automation_service
    _automation_service = service
