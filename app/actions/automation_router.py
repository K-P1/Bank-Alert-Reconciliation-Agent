"""REST API endpoints for automation control."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.actions.automation import get_automation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


# Request/Response models
class StartAutomationRequest(BaseModel):
    """Request to start automation."""

    interval_seconds: Optional[int] = Field(
        None, ge=60, le=86400, description="Override interval in seconds (60s-24h)"
    )
    enable_actions: bool = Field(
        True, description="Whether to enable post-processing actions"
    )


class AutomationStatusResponse(BaseModel):
    """Automation status response."""

    running: bool
    interval_seconds: int
    actions_enabled: bool
    metrics: dict


class RunOnceResponse(BaseModel):
    """Response from manual reconciliation run."""

    success: bool
    message: str
    stats: dict


# Endpoints


@router.get("/status", response_model=AutomationStatusResponse)
async def get_automation_status():
    """
    Get current automation status.

    Returns information about whether automation is running,
    configuration, and execution metrics.
    """
    automation = get_automation()
    status = automation.get_status()

    return AutomationStatusResponse(**status)


@router.post("/start")
async def start_automation(request: StartAutomationRequest | None = None):
    """
    Start the automation background service.

    Begins automatic reconciliation cycles at the configured interval.
    Will fetch emails, poll transactions, match, and execute actions.
    """
    automation = get_automation()

    if automation._running:
        return {
            "success": False,
            "message": "Automation is already running",
            "status": automation.get_status(),
        }

    # Update configuration if provided
    if request:
        if request.interval_seconds:
            automation.interval_seconds = request.interval_seconds
        automation.enable_actions = request.enable_actions

    await automation.start()

    logger.info(
        f"[API] Automation started via API "
        f"(interval: {automation.interval_seconds}s, "
        f"actions: {automation.enable_actions})"
    )

    return {
        "success": True,
        "message": f"Automation started (interval: {automation.interval_seconds}s)",
        "status": automation.get_status(),
    }


@router.post("/stop")
async def stop_automation():
    """
    Stop the automation background service.

    Gracefully stops the automation loop. Any in-progress
    reconciliation cycle will complete before stopping.
    """
    automation = get_automation()

    if not automation._running:
        return {
            "success": False,
            "message": "Automation is not running",
            "status": automation.get_status(),
        }

    await automation.stop()

    logger.info("[API] Automation stopped via API")

    return {
        "success": True,
        "message": "Automation stopped",
        "status": automation.get_status(),
    }


@router.post("/run-once", response_model=RunOnceResponse)
async def run_reconciliation_once():
    """
    Manually trigger a single reconciliation cycle.

    Executes the complete workflow once:
    1. Fetch new emails
    2. Poll new transactions
    3. Match unprocessed emails
    4. Execute post-processing actions

    This is useful for testing or manual reconciliation runs.
    """
    automation = get_automation()

    logger.info("[API] Manual reconciliation cycle requested via API")

    try:
        stats = await automation.run_once()

        success = len(stats.get("errors", [])) == 0

        return RunOnceResponse(
            success=success,
            message=(
                "Reconciliation cycle completed"
                if success
                else "Reconciliation completed with errors"
            ),
            stats=stats,
        )

    except Exception as e:
        logger.error(f"[API] Manual reconciliation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")


@router.patch("/config")
async def update_automation_config(
    interval_seconds: Optional[int] = Query(
        None, ge=60, le=86400, description="Update interval (60s-24h)"
    ),
    enable_actions: Optional[bool] = Query(None, description="Enable/disable actions"),
):
    """
    Update automation configuration.

    Changes will take effect on the next cycle if automation is running.
    """
    automation = get_automation()

    changes = []

    if interval_seconds is not None:
        old_interval = automation.interval_seconds
        automation.interval_seconds = interval_seconds
        changes.append(f"interval: {old_interval}s → {interval_seconds}s")

    if enable_actions is not None:
        old_actions = automation.enable_actions
        automation.enable_actions = enable_actions
        changes.append(
            f"actions: {'enabled' if old_actions else 'disabled'} → "
            f"{'enabled' if enable_actions else 'disabled'}"
        )

    if not changes:
        return {
            "success": False,
            "message": "No configuration changes provided",
            "config": {
                "interval_seconds": automation.interval_seconds,
                "enable_actions": automation.enable_actions,
            },
        }

    logger.info(f"[API] Automation config updated: {', '.join(changes)}")

    return {
        "success": True,
        "message": f"Configuration updated: {', '.join(changes)}",
        "config": {
            "interval_seconds": automation.interval_seconds,
            "enable_actions": automation.enable_actions,
        },
    }
