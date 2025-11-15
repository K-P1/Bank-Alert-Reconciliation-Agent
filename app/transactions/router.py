"""
Transaction poller API routes.

Provides endpoints to control the poller, view status, and access metrics.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

from app.transactions.poller import get_poller
from app.transactions.clients.mock_client import MockTransactionClient
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/transactions", tags=["transactions"])


class PollTriggerResponse(BaseModel):
    """Response for manual poll trigger."""

    run_id: str
    status: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class PollerStatusResponse(BaseModel):
    """Response for poller status."""

    running: bool
    enabled: bool
    last_poll_time: Optional[str]
    circuit_breaker: Dict[str, Any]
    current_run: Optional[Dict[str, Any]]
    last_run: Optional[Dict[str, Any]]
    metrics_24h: Dict[str, Any]
    success_rate_24h: float
    config: Dict[str, Any]


class MetricsResponse(BaseModel):
    """Response for metrics endpoint."""

    aggregate: Dict[str, Any]
    success_rate: float
    recent_runs: list[Dict[str, Any]]


@router.post("/poll", response_model=PollTriggerResponse)
async def trigger_poll():
    """
    Manually trigger a polling run.

    This endpoint runs a single poll immediately, regardless of
    the configured interval. Useful for testing or on-demand updates.

    In development mode with mock client only:
    - Automatically generates mock transaction data
    - Returns clear indication that data is mocked
    - Will not generate mock data in production
    """
    poller = get_poller()

    # Check if we're using mock client in development
    is_mock = isinstance(poller.client, MockTransactionClient)
    is_dev = settings.ENV == "development"

    if is_mock and is_dev:
        logger.warning(
            "🔔 MOCK DATA MODE: Using mock transaction client in development. "
            "Generating synthetic transactions for testing purposes."
        )

    try:
        result = await poller.poll_once()

        # Add mock data warning to response if applicable
        if is_mock and is_dev:
            result["data_source"] = "mock"
            result["warning"] = "⚠️ Mock data generated for development/testing"
            message = "Poll completed successfully (MOCK DATA)"
        else:
            result["data_source"] = "real"
            message = "Poll completed successfully"

        return PollTriggerResponse(
            run_id=result["run_id"],
            status=result["status"],
            message=message,
            details=result,
        )
    except Exception as e:
        # If we're in production and using mock, that's an error
        if is_mock and not is_dev:
            logger.error(
                "❌ CONFIGURATION ERROR: Mock client is active in production! "
                "Configure real transaction API client."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Transaction service not properly configured for production",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Poll failed: {str(e)}",
        )


@router.get("/status", response_model=PollerStatusResponse)
async def get_status():
    """
    Get current poller status and recent metrics.

    Returns:
        - Poller state (running, enabled)
        - Circuit breaker state
        - Current and last run details
        - 24-hour aggregate metrics
    """
    poller = get_poller()
    return poller.get_status()


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(hours: Optional[int] = None):
    """
    Get aggregate metrics for polling runs.

    Args:
        hours: Limit to last N hours (omit for all history)

    Returns:
        Aggregate metrics and recent run history
    """
    poller = get_poller()
    return poller.get_metrics(hours=hours)


@router.post("/start")
async def start_poller():
    """
    Start the polling loop.

    The poller will begin running on its configured interval.
    """
    poller = get_poller()

    if poller._running:
        return {"status": "already_running", "message": "Poller is already running"}

    await poller.start()
    return {"status": "started", "message": "Poller started successfully"}


@router.post("/stop")
async def stop_poller():
    """
    Stop the polling loop.

    The poller will complete any current run and then stop.
    """
    poller = get_poller()

    if not poller._running:
        return {"status": "not_running", "message": "Poller is not running"}

    await poller.stop()
    return {"status": "stopped", "message": "Poller stopped successfully"}


# Export poller for automation system
_poller = get_poller()
