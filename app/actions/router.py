"""REST API endpoints for actions and audit logs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.db.unit_of_work import UnitOfWork
from app.actions.models import WorkflowPolicy
from app.actions.executor import execute_actions_for_match

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions", tags=["actions"])


# Request/Response models
class WorkflowPolicyResponse(BaseModel):
    """Response model for workflow policy."""

    matched_actions: list[str]
    ambiguous_actions: list[str]
    unmatched_actions: list[str]
    review_actions: list[str]
    high_confidence_threshold: float
    low_confidence_threshold: float
    ambiguous_candidates_count: int
    escalate_if_amount_above: Optional[float]
    escalate_if_multiple_matches: bool
    escalate_if_no_reference: bool


class ActionAuditResponse(BaseModel):
    """Response model for action audit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action_id: str
    action_type: str
    match_id: int
    email_id: int
    transaction_id: Optional[int]
    match_status: str
    match_confidence: float
    match_outcome: str
    status: str
    outcome: str
    message: Optional[str]
    error: Optional[str]
    actor: str
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    retry_count: int


class ActionStatisticsResponse(BaseModel):
    """Response model for action statistics."""

    total: int
    success: int
    failed: int
    pending: int
    retrying: int
    by_type: dict[str, int]
    by_outcome: dict[str, int]
    avg_duration_ms: float


class TriggerActionsRequest(BaseModel):
    """Request to manually trigger actions for a match."""

    match_id: int = Field(..., description="Match ID to trigger actions for")
    actor: str = Field("manual", description="Actor triggering the actions")


class TriggerActionsResponse(BaseModel):
    """Response from manually triggering actions."""

    success: bool
    message: str
    actions_executed: int
    results: list[dict]


# Endpoints


@router.get("/policy", response_model=WorkflowPolicyResponse)
async def get_workflow_policy():
    """
    Get current workflow policy configuration.

    Returns the policy that determines which actions are taken
    for different match outcomes.
    """
    policy = WorkflowPolicy()

    return WorkflowPolicyResponse(
        matched_actions=[a.value for a in policy.matched_actions],
        ambiguous_actions=[a.value for a in policy.ambiguous_actions],
        unmatched_actions=[a.value for a in policy.unmatched_actions],
        review_actions=[a.value for a in policy.review_actions],
        high_confidence_threshold=policy.high_confidence_threshold,
        low_confidence_threshold=policy.low_confidence_threshold,
        ambiguous_candidates_count=policy.ambiguous_candidates_count,
        escalate_if_amount_above=policy.escalate_if_amount_above,
        escalate_if_multiple_matches=policy.escalate_if_multiple_matches,
        escalate_if_no_reference=policy.escalate_if_no_reference,
    )


@router.get("/audits", response_model=list[ActionAuditResponse])
async def get_action_audits(
    match_id: Optional[int] = Query(None, description="Filter by match ID"),
    email_id: Optional[int] = Query(None, description="Filter by email ID"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    outcome: Optional[str] = Query(None, description="Filter by match outcome"),
    actor: Optional[str] = Query(None, description="Filter by actor"),
    since_hours: Optional[int] = Query(
        None, description="Only show audits from last N hours"
    ),
    limit: int = Query(100, le=1000, description="Maximum results to return"),
):
    """
    Get action audit logs with optional filtering.

    Retrieve execution history of post-processing actions with details
    about what was executed, when, by whom, and the outcome.
    """
    async with UnitOfWork() as uow:
        # Build filters
        if match_id:
            audits = await uow.action_audits.get_by_match_id(match_id, action_type)
        elif email_id:
            audits = await uow.action_audits.get_by_email_id(email_id, action_type)
        elif outcome:
            since = None
            if since_hours:
                since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            audits = await uow.action_audits.get_by_outcome(outcome, since, limit)
        elif actor:
            since = None
            if since_hours:
                since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            audits = await uow.action_audits.get_by_actor(actor, since, limit)
        elif status == "failed":
            since = None
            if since_hours:
                since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            audits = await uow.action_audits.get_failed_actions(since, limit)
        elif status == "pending":
            audits = await uow.action_audits.get_pending_actions(limit=limit)
        else:
            # Get all recent audits
            filters = {}
            if since_hours:
                filters["started_at__gte"] = datetime.now(timezone.utc) - timedelta(
                    hours=since_hours
                )
            if status:
                filters["status"] = status
            audits = await uow.action_audits.filter(**filters, limit=limit)

    return [ActionAuditResponse.model_validate(audit) for audit in audits]


@router.get("/audits/{action_id}", response_model=ActionAuditResponse)
async def get_action_audit(action_id: str):
    """
    Get a specific action audit by action ID.
    """
    async with UnitOfWork() as uow:
        audit = await uow.action_audits.get_by_action_id(action_id)

        if not audit:
            raise HTTPException(status_code=404, detail="Action audit not found")

    return ActionAuditResponse.model_validate(audit)


@router.get("/statistics", response_model=ActionStatisticsResponse)
async def get_action_statistics(
    since_hours: Optional[int] = Query(24, description="Statistics for last N hours"),
):
    """
    Get action execution statistics.

    Provides aggregate metrics about action execution including
    success/failure rates, average duration, breakdown by type, etc.
    """
    since = None
    if since_hours:
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    async with UnitOfWork() as uow:
        stats = await uow.action_audits.get_statistics(since)

    return ActionStatisticsResponse(**stats)


@router.post("/trigger", response_model=TriggerActionsResponse)
async def trigger_actions_for_match(request: TriggerActionsRequest):
    """
    Manually trigger actions for a match.

    Useful for retrying failed actions or triggering actions
    for matches that were processed before actions were enabled.
    """
    logger.info(
        f"[API] Manual action trigger requested for match {request.match_id} "
        f"by {request.actor}"
    )

    async with UnitOfWork() as uow:
        # Get match details
        match = await uow.matches.get_by_id(request.match_id)
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        # Get email for metadata
        email = await uow.emails.get_by_id(match.email_id)
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        # Build metadata
        metadata = {
            "amount": float(email.amount) if email.amount else 0,
            "currency": email.currency or "NGN",
            "reference": email.reference or "N/A",
            "sender": email.sender,
            "manual_trigger": True,
        }

        # Execute actions (need session from base)
        from app.db.base import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as session:
                results = await execute_actions_for_match(
                    session=session,
                    match_id=match.id,
                    email_id=match.email_id,
                    transaction_id=match.transaction_id,
                    match_status=match.status,
                    confidence=float(match.confidence),
                    metadata=metadata,
                    actor=request.actor,
                )

            sum(1 for r in results if r.status.value == "success")

            return TriggerActionsResponse(
                success=True,
                message=f"Executed {len(results)} actions for match {request.match_id}",
                actions_executed=len(results),
                results=[
                    {
                        "action_type": r.action_type.value,
                        "status": r.status.value,
                        "outcome": r.outcome,
                        "message": r.message,
                    }
                    for r in results
                ],
            )

        except Exception as e:
            logger.error(
                f"[API] Failed to execute actions for match {request.match_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to execute actions: {str(e)}",
            )


@router.delete("/audits/cleanup")
async def cleanup_old_audits(
    retention_days: int = Query(
        90, ge=1, le=365, description="Delete audits older than N days"
    ),
):
    """
    Clean up old audit logs.

    Deletes audit logs older than the specified retention period.
    Use with caution in production.
    """
    logger.info(f"[API] Cleanup requested for audits older than {retention_days} days")

    async with UnitOfWork() as uow:
        deleted_count = await uow.action_audits.delete_old_audits(retention_days)
        await uow.commit()

    logger.info(f"[API] Deleted {deleted_count} old audit records")

    return {
        "success": True,
        "message": f"Deleted {deleted_count} audit records older than {retention_days} days",
        "deleted_count": deleted_count,
    }
