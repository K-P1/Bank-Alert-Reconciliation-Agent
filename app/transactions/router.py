"""
Transaction poller API routes.

Provides endpoints to control the poller, view status, and access metrics.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.transactions.poller import get_poller

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
    """
    poller = get_poller()

    try:
        result = await poller.poll_once()

        return PollTriggerResponse(
            run_id=result["run_id"],
            status=result["status"],
            message="Poll completed successfully",
            details=result,
        )
    except Exception as e:
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
