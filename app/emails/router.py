"""FastAPI router for email fetcher management."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.emails.mock_email_generator import MockEmailGenerator
from app.db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/emails", tags=["emails"])

# Global fetcher instance (set by main app)
_fetcher = None


def set_fetcher(fetcher):
    """Set the global fetcher instance."""
    global _fetcher
    _fetcher = fetcher


class FetchResponse(BaseModel):
    """Response from fetch operation."""

    status: str
    run_id: str | None = None
    emails_fetched: int | None = None
    emails_processed: int | None = None
    emails_stored: int | None = None
    error: str | None = None


class StatusResponse(BaseModel):
    """Response from status endpoint."""

    running: bool
    enabled: bool
    poll_interval_minutes: int
    llm_enabled: bool
    last_run: dict | None = None
    aggregate_metrics: dict


@router.post("/fetch", response_model=FetchResponse, status_code=status.HTTP_200_OK)
async def trigger_fetch():
    """Trigger a manual email fetch cycle.

    In development mode when IMAP is not configured:
    - Automatically generates mock email data
    - Returns clear indication that data is mocked
    - Will not generate mock data in production

    Returns:
        Fetch results
    """
    # Check if IMAP is configured
    imap_configured = all(
        [
            settings.IMAP_HOST,
            settings.IMAP_USER,
            settings.IMAP_PASS,
        ]
    )
    is_dev = settings.ENV == "development"

    # If IMAP not configured and we're in development, use mock data
    if not imap_configured and is_dev:
        logger.warning(
            "🔔 MOCK DATA MODE: IMAP not configured in development. "
            "Generating synthetic bank alert emails for testing purposes."
        )

        try:
            # Generate mock emails
            generator = MockEmailGenerator()
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)

            mock_emails = generator.generate_emails(
                count=settings.MOCK_EMAIL_COUNT,  # Use config value
                start_time=start_time,
                end_time=end_time,
            )

            # Store mock emails in database
            run_id = f"mock-{uuid.uuid4().hex[:8]}"
            stored_count = 0
            skipped_count = 0

            async with UnitOfWork() as uow:
                for email_data in mock_emails:
                    try:
                        # Check if exists
                        existing = await uow.emails.get_by_message_id(
                            email_data["message_id"]
                        )
                        if existing:
                            skipped_count += 1
                            continue

                        # Create email
                        await uow.emails.create(**email_data)
                        stored_count += 1

                    except Exception as e:
                        logger.error(f"Error storing mock email: {e}")

                await uow.commit()

            logger.info(
                f"[EMAILS] ✓ Mock data generated: {stored_count} emails stored, "
                f"{skipped_count} skipped (duplicates)"
            )

            return FetchResponse(
                status="success",
                run_id=run_id,
                emails_fetched=len(mock_emails),
                emails_processed=len(mock_emails),
                emails_stored=stored_count,
                error=(
                    None
                    if stored_count > 0
                    else "⚠️ MOCK DATA: Generated for development/testing only"
                ),
            )

        except Exception as e:
            logger.error(f"[EMAILS] Mock data generation failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Mock email generation failed: {str(e)}",
            )

    # If IMAP not configured and we're in production, that's an error
    if not imap_configured and not is_dev:
        logger.error(
            "❌ CONFIGURATION ERROR: IMAP not configured in production! "
            "Set IMAP_HOST, IMAP_USER, and IMAP_PASS environment variables."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service not properly configured for production",
        )

    # Normal IMAP fetch
    if not _fetcher:
        logger.error("[EMAILS] Fetch requested but fetcher not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    logger.info("[EMAILS] Manual fetch triggered via API")
    result = await _fetcher.fetch_once()

    return FetchResponse(**result)


# Individual status removed - use unified /automation/status instead


# Individual start/stop removed - use unified /automation/start and /automation/stop instead


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_metrics():
    """Get detailed metrics from recent fetch runs.

    Returns:
        Recent run metrics or disabled status if fetcher not initialized
    """
    if not _fetcher:
        # Return disabled status instead of 503 error
        return {
            "enabled": False,
            "message": "Email fetcher not initialized (IMAP settings not configured)",
            "recent_runs": [],
            "aggregate": {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "total_emails_fetched": 0,
                "total_emails_stored": 0,
                "average_duration_seconds": 0,
            },
        }

    recent_runs = _fetcher.metrics.get_recent_runs(count=10)

    return {
        "enabled": True,
        "recent_runs": [
            {
                "run_id": run.run_id,
                "started_at": run.started_at.isoformat(),
                "duration_seconds": run.duration_seconds,
                "status": run.status,
                "emails_fetched": run.emails_fetched,
                "emails_filtered": run.emails_filtered,
                "emails_parsed": run.emails_parsed,
                "emails_stored": run.emails_stored,
                "avg_confidence": run.avg_confidence,
                "parsing_methods": {
                    "llm": run.parsed_with_llm,
                    "regex": run.parsed_with_regex,
                    "hybrid": run.parsed_hybrid,
                },
                "field_extraction": {
                    "amount": run.amount_extracted_count,
                    "currency": run.currency_extracted_count,
                    "reference": run.reference_extracted_count,
                    "timestamp": run.timestamp_extracted_count,
                },
            }
            for run in recent_runs
        ],
        "aggregate": _fetcher.metrics.get_aggregate_metrics(),
    }
