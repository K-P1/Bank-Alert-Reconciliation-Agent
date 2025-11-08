"""Email fetcher service for polling and processing emails."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.db.models.email import Email
from app.db.unit_of_work import UnitOfWork
from app.emails.imap_connector import IMAPConnector
from app.emails.metrics import ParserMetrics
from app.emails.parser import HybridParser

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.emails.config import EmailConfig

logger = logging.getLogger(__name__)


class EmailFetcher:
    """Email fetcher service with background polling."""

    def __init__(self, settings: Settings, config: EmailConfig):
        """Initialize email fetcher.

        Args:
            settings: Application settings
            config: Email configuration
        """
        self.settings = settings
        self.config = config
        self.parser = HybridParser(config)
        self.metrics = ParserMetrics()

        # Validate IMAP settings
        if not all([settings.IMAP_HOST, settings.IMAP_USER, settings.IMAP_PASS]):
            raise ValueError(
                "IMAP settings not configured (IMAP_HOST, IMAP_USER, IMAP_PASS required)"
            )

        # Background task management
        self._task: asyncio.Task | None = None
        self._running = False
        self._poll_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start background email polling."""
        if self._running:
            logger.warning("[FETCHER] Email fetcher already running")
            return

        if not self.config.fetcher.enabled:
            logger.info("[FETCHER] Email fetcher disabled in configuration")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"[FETCHER] ✓ Email fetcher started | "
            f"Poll interval: {self.config.fetcher.poll_interval_minutes} minutes"
        )

        # Run immediately if configured
        if self.config.fetcher.start_immediately:
            logger.info("[FETCHER] Running initial fetch immediately")
            asyncio.create_task(self.fetch_once())

    async def stop(self) -> None:
        """Stop background email polling."""
        if not self._running:
            logger.debug("[FETCHER] Email fetcher not running")
            return

        logger.info("[FETCHER] Stopping email fetcher...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("[FETCHER] ✓ Email fetcher stopped")

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._running:
            try:
                await self.fetch_once()
            except Exception as e:
                logger.error(f"Error in email polling loop: {e}", exc_info=True)

            # Wait for next poll
            await asyncio.sleep(self.config.fetcher.poll_interval_minutes * 60)

    async def fetch_once(self) -> dict:
        """Execute a single fetch cycle.

        Returns:
            Dict with run results
        """
        # Prevent concurrent polls
        if self._poll_lock.locked():
            logger.warning("[FETCHER] Poll already in progress, skipping")
            return {"status": "skipped", "reason": "poll_in_progress"}

        async with self._poll_lock:
            run_id = f"fetch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
            self.metrics.start_run(run_id)

            logger.info(
                f"[FETCHER] ========== Starting fetch cycle: {run_id} =========="
            )

            try:
                # Fetch emails from IMAP
                logger.info("[FETCHER] Connecting to IMAP and fetching emails...")
                raw_emails = await asyncio.to_thread(self._fetch_from_imap)
                self.metrics.record_fetch(len(raw_emails))

                logger.info(f"[FETCHER] Fetched {len(raw_emails)} emails from IMAP")

                if not raw_emails:
                    logger.info("[FETCHER] ✓ No new emails to process")
                    self.metrics.end_run("SUCCESS")
                    return {
                        "status": "success",
                        "run_id": run_id,
                        "emails_fetched": 0,
                        "emails_processed": 0,
                    }

                # Parse and store emails
                logger.info(f"[FETCHER] Processing {len(raw_emails)} emails...")
                emails_processed = 0
                emails_stored = 0

                for idx, raw_email in enumerate(raw_emails, 1):
                    logger.debug(
                        f"[FETCHER] Processing email {idx}/{len(raw_emails)}: {raw_email.message_id}"
                    )
                    try:
                        # Parse email
                        parsed_email = await self.parser.parse_email(raw_email)

                        if parsed_email is None:
                            # Filtered out
                            logger.debug(f"[FETCHER] Email {idx} filtered out")
                            self.metrics.record_filtered()
                            continue

                        # Record classification
                        self.metrics.record_classified(parsed_email.is_alert)

                        # Record parsing
                        self.metrics.record_parsed(
                            parsing_method=parsed_email.parsing_method,
                            confidence=parsed_email.confidence,
                            fields={
                                "amount": parsed_email.amount,
                                "currency": parsed_email.currency,
                                "reference": parsed_email.reference,
                                "email_timestamp": parsed_email.email_timestamp,
                            },
                        )

                        # Store to database
                        stored = await self._store_email(parsed_email)
                        if stored:
                            self.metrics.record_stored()
                            emails_stored += 1
                            logger.debug(f"[FETCHER] ✓ Email {idx} stored successfully")
                        else:
                            logger.debug(f"[FETCHER] Email {idx} skipped (duplicate)")

                        emails_processed += 1

                    except Exception as e:
                        logger.error(
                            f"[FETCHER] Error processing email {idx} ({raw_email.message_id}): {e}"
                        )
                        self.metrics.record_failed(str(e))
                        continue

                logger.info(
                    f"[FETCHER] Processing complete | "
                    f"Fetched: {len(raw_emails)} | "
                    f"Processed: {emails_processed} | "
                    f"Stored: {emails_stored}"
                )

                # Determine final status
                from typing import Literal

                status: Literal["SUCCESS", "PARTIAL", "FAILED"]
                if emails_stored == len(raw_emails):
                    status = "SUCCESS"
                elif emails_stored > 0:
                    status = "PARTIAL"
                else:
                    status = "FAILED"

                self.metrics.end_run(status)

                result = {
                    "status": status.lower(),
                    "run_id": run_id,
                    "emails_fetched": len(raw_emails),
                    "emails_processed": emails_processed,
                    "emails_stored": emails_stored,
                }

                logger.info(
                    f"[FETCHER] ========== ✓ Fetch cycle {run_id} completed ========== | "
                    f"Status: {status} | Fetched: {len(raw_emails)} | "
                    f"Processed: {emails_processed} | Stored: {emails_stored}"
                )

                return result

            except Exception as e:
                logger.error(
                    f"[FETCHER] ✗ Fetch cycle {run_id} failed: {e}", exc_info=True
                )
                self.metrics.end_run("FAILED", error_message=str(e))
                return {
                    "status": "failed",
                    "run_id": run_id,
                    "error": str(e),
                }

    def _fetch_from_imap(self) -> list:
        """Fetch emails from IMAP (runs in thread).

        Returns:
            List of raw emails
        """
        # Type narrowing - these are validated in __init__
        if (
            not self.settings.IMAP_HOST
            or not self.settings.IMAP_USER
            or not self.settings.IMAP_PASS
        ):
            raise RuntimeError("IMAP settings not configured")

        with IMAPConnector(
            host=self.settings.IMAP_HOST,
            user=self.settings.IMAP_USER,
            password=self.settings.IMAP_PASS,
            config=self.config.fetcher,
        ) as connector:
            return connector.fetch_unread_emails(limit=self.config.fetcher.batch_size)

    async def _store_email(self, parsed_email) -> bool:
        """Store parsed email to database.

        Args:
            parsed_email: Parsed email to store

        Returns:
            True if stored successfully
        """
        try:
            async with UnitOfWork() as uow:
                # Check if already exists
                existing = await uow.emails.get_by_message_id(parsed_email.message_id)
                if existing:
                    logger.debug(f"Email already exists: {parsed_email.message_id}")
                    return False

                # Create email record
                email = Email(
                    message_id=parsed_email.message_id,
                    sender=parsed_email.sender,
                    subject=parsed_email.subject,
                    body=parsed_email.body,
                    amount=parsed_email.amount,
                    currency=parsed_email.currency,
                    reference=parsed_email.reference,
                    email_timestamp=parsed_email.email_timestamp,
                    received_at=parsed_email.received_at,
                    parsed_at=parsed_email.parsed_at,
                    is_processed=parsed_email.is_alert,
                    confidence=parsed_email.confidence,
                    parsing_method=parsed_email.parsing_method,
                )

                await uow.emails.create(
                    message_id=email.message_id,
                    sender=email.sender,
                    subject=email.subject,
                    body=email.body,
                    amount=email.amount,
                    currency=email.currency,
                    reference=email.reference,
                    email_timestamp=email.email_timestamp,
                    received_at=email.received_at,
                    parsed_at=email.parsed_at,
                    is_processed=email.is_processed,
                    confidence=email.confidence,
                    parsing_method=email.parsing_method,
                )

                await uow.commit()
                logger.debug(f"Email stored: {parsed_email.message_id}")
                return True

        except Exception as e:
            logger.error(f"Error storing email: {e}")
            return False

    def get_status(self) -> dict:
        """Get fetcher status and metrics.

        Returns:
            Dict with status information
        """
        last_run = self.metrics.get_last_run()
        aggregate = self.metrics.get_aggregate_metrics()

        return {
            "running": self._running,
            "enabled": self.config.fetcher.enabled,
            "poll_interval_minutes": self.config.fetcher.poll_interval_minutes,
            "llm_enabled": self.config.llm.enabled,
            "last_run": (
                {
                    "run_id": last_run.run_id,
                    "started_at": last_run.started_at.isoformat(),
                    "status": last_run.status,
                    "emails_fetched": last_run.emails_fetched,
                    "emails_stored": last_run.emails_stored,
                    "duration_seconds": last_run.duration_seconds,
                }
                if last_run
                else None
            ),
            "aggregate_metrics": aggregate,
        }
