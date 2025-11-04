"""FastAPI router for email fetcher management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

    Returns:
        Fetch results
    """
    if not _fetcher:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    logger.info("Manual fetch triggered via API")
    result = await _fetcher.fetch_once()

    return FetchResponse(**result)


@router.get("/status", response_model=StatusResponse, status_code=status.HTTP_200_OK)
async def get_status():
    """Get email fetcher status and metrics.

    Returns:
        Status and metrics
    """
    if not _fetcher:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    status_data = _fetcher.get_status()
    return StatusResponse(**status_data)


@router.post("/start", status_code=status.HTTP_200_OK)
async def start_fetcher():
    """Start the email fetcher background service.

    Returns:
        Success message
    """
    if not _fetcher:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    await _fetcher.start()
    return {"status": "started", "message": "Email fetcher started"}


@router.post("/stop", status_code=status.HTTP_200_OK)
async def stop_fetcher():
    """Stop the email fetcher background service.

    Returns:
        Success message
    """
    if not _fetcher:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    await _fetcher.stop()
    return {"status": "stopped", "message": "Email fetcher stopped"}


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_metrics():
    """Get detailed metrics from recent fetch runs.

    Returns:
        Recent run metrics
    """
    if not _fetcher:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email fetcher not initialized",
        )

    recent_runs = _fetcher.metrics.get_recent_runs(count=10)

    return {
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
