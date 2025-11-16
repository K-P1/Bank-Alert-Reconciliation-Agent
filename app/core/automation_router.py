"""FastAPI router for unified automation control.

Provides centralized endpoints for the unified automation service that
coordinates email fetching, transaction polling, and reconciliation matching.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import logging

from app.core.automation import get_automation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


class AutomationStatusResponse(BaseModel):
    """Response for automation status endpoint."""

    running: bool
    enabled: bool
    interval_seconds: int
    cycles_completed: int
    last_cycle: dict | None
    errors_count: int
    email_fetcher: dict
    transaction_poller: dict
    match_engine: dict


@router.get(
    "/status", response_model=AutomationStatusResponse, status_code=status.HTTP_200_OK
)
async def get_automation_status():
    """Get unified automation service status.

    Returns status for all three components:
    - Email fetcher
    - Transaction poller
    - Match engine

    Returns:
        Comprehensive automation status
    """
    service = get_automation_service()
    status_data = service.get_status()
    return AutomationStatusResponse(**status_data)


@router.post("/start", status_code=status.HTTP_200_OK)
async def start_automation():
    """Start the unified automation service.

    Begins automated cycles of:
    1. Fetch new emails
    2. Poll new transactions
    3. Run reconciliation matching

    Returns:
        Success message
    """
    service = get_automation_service()

    if service._running:
        logger.info("[AUTOMATION] Already running")
        return {
            "status": "already_running",
            "message": "Automation service is already running",
        }

    logger.info("[AUTOMATION] Starting automation service via API")
    await service.start()
    return {"status": "started", "message": "Automation service started successfully"}


@router.post("/stop", status_code=status.HTTP_200_OK)
async def stop_automation():
    """Stop the unified automation service.

    Completes current cycle (if running) then stops.

    Returns:
        Success message
    """
    service = get_automation_service()

    if not service._running:
        logger.info("[AUTOMATION] Not running")
        return {"status": "not_running", "message": "Automation service is not running"}

    logger.info("[AUTOMATION] Stopping automation service via API")
    await service.stop()
    return {"status": "stopped", "message": "Automation service stopped successfully"}


@router.post("/match", status_code=status.HTTP_200_OK)
async def trigger_match():
    """Manually trigger reconciliation matching.

    Runs the matching engine on currently unmatched emails and transactions
    without waiting for the automated cycle.

    Returns:
        Match results
    """
    service = get_automation_service()

    try:
        logger.info("[AUTOMATION] Manual match triggered via API")
        result = await service.run_matching()

        return {
            "status": "success",
            "message": "Manual matching completed",
            "matches_created": result.get("matches_created", 0),
            "emails_matched": result.get("emails_matched", 0),
            "details": result,
        }
    except Exception as e:
        logger.error(f"[AUTOMATION] Manual match failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Matching failed: {str(e)}",
        )
