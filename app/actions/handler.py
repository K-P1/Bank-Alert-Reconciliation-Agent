"""Action handler orchestrator for post-processing."""

from __future__ import annotations

import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.config import get_actions_config
from app.actions.models import (
    ActionContext,
    ActionResult,
    ActionStatus,
    ActionType,
    MatchOutcome,
    NotificationPayload,
    TicketPayload,
    WebhookPayload,
    WorkflowPolicy,
)
from app.actions.connectors import (
    DatabaseConnector,
    EmailNotificationConnector,
    TicketConnector,
    CRMConnector,
    WebhookConnector,
)
from app.db.models.action_audit import ActionAudit
from app.db.repositories.action_audit_repository import ActionAuditRepository

logger = logging.getLogger(__name__)


class ActionHandler:
    """
    Orchestrates post-processing actions based on match outcomes.

    Handles:
    - Determining which actions to take based on match status
    - Executing actions with retry logic
    - Auditing all actions
    - Escalation workflows
    """

    def __init__(
        self,
        session: AsyncSession,
        policy: Optional[WorkflowPolicy] = None,
    ):
        """
        Initialize action handler.

        Args:
            session: Database session
            policy: Workflow policy (defaults to standard policy)
        """
        self.session = session
        self.policy = policy or WorkflowPolicy()
        self.config = get_actions_config()

        # Initialize connectors
        self.db_connector = DatabaseConnector()
        self.email_connector = EmailNotificationConnector()
        self.ticket_connector = TicketConnector()
        self.crm_connector = CRMConnector()
        self.webhook_connector = WebhookConnector()

        # Initialize audit repository
        self.audit_repo = ActionAuditRepository(ActionAudit, self.session)

        logger.info("ActionHandler initialized with policy")

    async def process_match_result(
        self,
        match_id: int,
        email_id: int,
        transaction_id: Optional[int],
        match_status: str,
        confidence: float,
        metadata: Optional[dict[str, Any]] = None,
        actor: str = "system",
    ) -> list[ActionResult]:
        """
        Process a match result and execute appropriate actions.

        Args:
            match_id: Match database ID
            email_id: Email database ID
            transaction_id: Transaction database ID (if matched)
            match_status: Match status (matched, review, rejected, no_candidates)
            confidence: Match confidence score
            metadata: Additional context metadata
            actor: Actor triggering the actions

        Returns:
            List of action results
        """
        logger.info(
            f"[ACTIONS] Processing match result | "
            f"Match ID: {match_id} | Status: {match_status} | "
            f"Confidence: {confidence:.2f}"
        )

        # Determine match outcome
        outcome = self._determine_outcome(match_status, confidence, metadata or {})

        # Build action context
        context = ActionContext(
            match_id=match_id,
            email_id=email_id,
            transaction_id=transaction_id,
            match_status=match_status,
            confidence=confidence,
            match_outcome=outcome,
            actor=actor,
            metadata=metadata or {},
        )

        # Get actions to execute
        actions = self._get_actions_for_context(context)

        logger.info(
            f"[ACTIONS] Executing {len(actions)} actions for outcome: {outcome.value}"
        )

        # Execute actions
        results = []
        for action_type in actions:
            try:
                result = await self._execute_action(action_type, context)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"[ACTIONS] Failed to execute {action_type.value}: {e}",
                    exc_info=True,
                )
                results.append(
                    ActionResult(
                        action_type=action_type,
                        status=ActionStatus.FAILED,
                        outcome="execution_error",
                        message=f"Failed to execute {action_type.value}",
                        error=str(e),
                    )
                )

        logger.info(
            f"[ACTIONS] ✓ Completed {len(results)} actions | "
            f"Success: {sum(1 for r in results if r.status == ActionStatus.SUCCESS)} | "
            f"Failed: {sum(1 for r in results if r.status == ActionStatus.FAILED)}"
        )

        return results

    def _determine_outcome(
        self,
        match_status: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> MatchOutcome:
        """Determine match outcome category from status and confidence."""
        if match_status == "matched":
            # Check if it's truly high confidence or ambiguous
            alternative_count = metadata.get("alternative_candidates_count", 0)
            if alternative_count >= self.policy.ambiguous_candidates_count:
                return MatchOutcome.AMBIGUOUS
            if confidence < self.policy.high_confidence_threshold:
                return MatchOutcome.AMBIGUOUS
            return MatchOutcome.MATCHED

        elif match_status == "review":
            return MatchOutcome.REVIEW

        elif match_status == "no_candidates":
            return MatchOutcome.UNMATCHED

        elif match_status == "rejected":
            return MatchOutcome.REJECTED

        else:
            # Default to review for unknown statuses
            return MatchOutcome.REVIEW

    def _get_actions_for_context(self, context: ActionContext) -> list[ActionType]:
        """Get list of actions to execute based on context."""
        # Get base actions for outcome
        actions = self.policy.get_actions_for_outcome(context.match_outcome)

        # Check if escalation needed
        if self.policy.should_escalate(context):
            logger.info(f"[ACTIONS] Escalation triggered for match {context.match_id}")
            if ActionType.ESCALATE not in actions:
                actions.append(ActionType.ESCALATE)

        return actions

    async def _execute_action(
        self,
        action_type: ActionType,
        context: ActionContext,
    ) -> ActionResult:
        """Execute a single action with audit logging."""
        action_id = f"act-{uuid.uuid4().hex[:12]}"
        start_time = datetime.now(timezone.utc)

        logger.debug(f"[ACTION] Executing {action_type.value} | Action ID: {action_id}")

        # Create audit record (pending)
        audit = await self._create_audit_record(
            action_id, action_type, context, start_time
        )

        try:
            # Execute the action
            if action_type == ActionType.MARK_VERIFIED:
                result = await self._mark_verified(context)
            elif action_type == ActionType.UPDATE_STATUS:
                result = await self._update_status(context)
            elif action_type == ActionType.NOTIFY_CRM:
                result = await self._notify_crm(context)
            elif action_type == ActionType.CREATE_TICKET:
                result = await self._create_ticket(context)
            elif action_type == ActionType.SEND_EMAIL:
                result = await self._send_email(context)
            elif action_type == ActionType.FLAG_UNMATCHED:
                result = await self._flag_unmatched(context)
            elif action_type == ActionType.ESCALATE:
                result = await self._escalate(context)
            elif action_type == ActionType.SEND_WEBHOOK:
                result = await self._send_webhook(context)
            else:
                result = ActionResult(
                    action_type=action_type,
                    status=ActionStatus.SKIPPED,
                    outcome="not_implemented",
                    message=f"Action {action_type.value} not yet implemented",
                )

            # Calculate duration
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            result.duration_ms = duration_ms

            # Update audit record with result
            await self._update_audit_record(audit, result, end_time, duration_ms)

            return result

        except Exception as e:
            logger.error(
                f"[ACTION] {action_type.value} failed: {e}",
                exc_info=True,
            )

            # Update audit with error
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            result = ActionResult(
                action_type=action_type,
                status=ActionStatus.FAILED,
                outcome="execution_error",
                message="Action execution failed",
                error=str(e),
                duration_ms=duration_ms,
            )

            await self._update_audit_record(audit, result, end_time, duration_ms)
            return result

    async def _create_audit_record(
        self,
        action_id: str,
        action_type: ActionType,
        context: ActionContext,
        started_at: datetime,
    ) -> ActionAudit:
        """Create initial audit record."""
        audit = ActionAudit(
            action_id=action_id,
            action_type=action_type.value,
            match_id=context.match_id,
            email_id=context.email_id,
            transaction_id=context.transaction_id,
            match_status=context.match_status,
            match_confidence=context.confidence,
            match_outcome=context.match_outcome.value,
            status="pending",
            outcome="pending",
            message="Action execution started",
            actor=context.actor,
            started_at=started_at,
            action_metadata=json.dumps(context.metadata) if context.metadata else None,
        )

        self.session.add(audit)
        await self.session.commit()
        await self.session.refresh(audit)

        return audit

    async def _update_audit_record(
        self,
        audit: ActionAudit,
        result: ActionResult,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        """Update audit record with execution result."""
        audit.status = result.status.value
        audit.outcome = result.outcome
        audit.message = result.message
        audit.error = result.error
        audit.completed_at = completed_at
        audit.duration_ms = duration_ms
        audit.retry_count = result.retry_count

        if result.metadata:
            # Merge with existing metadata
            existing_metadata = (
                json.loads(audit.action_metadata) if audit.action_metadata else {}
            )
            existing_metadata.update(result.metadata)
            audit.action_metadata = json.dumps(existing_metadata)

        await self.session.commit()

    # Action implementations

    async def _mark_verified(self, context: ActionContext) -> ActionResult:
        """Mark transaction as verified."""
        if not context.transaction_id:
            return ActionResult(
                action_type=ActionType.MARK_VERIFIED,
                status=ActionStatus.SKIPPED,
                outcome="no_transaction",
                message="No transaction to verify",
            )

        return await self.db_connector.execute(context.transaction_id, self.session)

    async def _update_status(self, context: ActionContext) -> ActionResult:
        """Update match status."""
        # Status is already updated by matching engine, just log it
        return ActionResult(
            action_type=ActionType.UPDATE_STATUS,
            status=ActionStatus.SUCCESS,
            outcome="status_updated",
            message=f"Match status: {context.match_status}",
            metadata={"match_status": context.match_status},
        )

    async def _notify_crm(self, context: ActionContext) -> ActionResult:
        """Send notification to CRM."""
        crm_data = {
            "match_id": context.match_id,
            "email_id": context.email_id,
            "transaction_id": context.transaction_id,
            "status": context.match_status,
            "confidence": context.confidence,
            "amount": context.metadata.get("amount"),
            "currency": context.metadata.get("currency"),
            "reference": context.metadata.get("reference"),
        }

        return await self.crm_connector.execute(crm_data)

    async def _create_ticket(self, context: ActionContext) -> ActionResult:
        """Create ticket for manual review."""
        # Build ticket details
        if context.match_outcome == MatchOutcome.AMBIGUOUS:
            title = f"Ambiguous Match Requires Review - Match #{context.match_id}"
            description = (
                f"Multiple candidate transactions found or low confidence match.\n\n"
                f"Match ID: {context.match_id}\n"
                f"Email ID: {context.email_id}\n"
                f"Confidence: {context.confidence:.2%}\n"
                f"Amount: {context.metadata.get('amount')} {context.metadata.get('currency')}\n"
                f"Reference: {context.metadata.get('reference')}\n"
                f"Alternative candidates: {context.metadata.get('alternative_candidates_count', 0)}\n\n"
                f"Please review and manually match the correct transaction."
            )
            priority = "high" if context.confidence < 0.5 else "medium"
            category = "ambiguous_match"

        elif context.match_outcome == MatchOutcome.UNMATCHED:
            title = f"Unmatched Email Alert - Email #{context.email_id}"
            description = (
                f"No matching transaction found for email alert.\n\n"
                f"Email ID: {context.email_id}\n"
                f"Amount: {context.metadata.get('amount')} {context.metadata.get('currency')}\n"
                f"Reference: {context.metadata.get('reference')}\n"
                f"Sender: {context.metadata.get('sender')}\n\n"
                f"Please investigate and take appropriate action."
            )
            priority = "medium"
            category = "unmatched_alert"

        else:
            title = f"Match Review Required - Match #{context.match_id}"
            description = (
                f"Manual review required for this match.\n\n"
                f"Match ID: {context.match_id}\n"
                f"Status: {context.match_status}\n"
                f"Confidence: {context.confidence:.2%}\n"
            )
            priority = "medium"
            category = "review_required"

        payload = TicketPayload(
            title=title,
            description=description,
            priority=priority,
            category=category,
            metadata=context.metadata,
        )

        return await self.ticket_connector.execute(payload)

    async def _send_email(self, context: ActionContext) -> ActionResult:
        """Send email notification."""
        # Determine recipient
        if context.match_outcome == MatchOutcome.AMBIGUOUS:
            recipient = self.config.OPERATIONS_EMAIL or "operations@example.com"
            subject = f"Ambiguous Match Alert - Match #{context.match_id}"
            message = (
                f"An ambiguous match requires your review:\n\n"
                f"Match ID: {context.match_id}\n"
                f"Confidence: {context.confidence:.2%}\n"
                f"Amount: {context.metadata.get('amount')} {context.metadata.get('currency')}\n"
                f"View details: /matches/{context.match_id}"
            )
            priority = "high"

        elif context.match_outcome == MatchOutcome.UNMATCHED:
            recipient = self.config.OPERATIONS_EMAIL or "operations@example.com"
            subject = f"Unmatched Email Alert - Email #{context.email_id}"
            message = (
                f"No matching transaction found:\n\n"
                f"Email ID: {context.email_id}\n"
                f"Amount: {context.metadata.get('amount')} {context.metadata.get('currency')}\n"
                f"View details: /emails/{context.email_id}"
            )
            priority = "normal"

        else:
            recipient = self.config.OPERATIONS_EMAIL or "operations@example.com"
            subject = f"Match Status Update - Match #{context.match_id}"
            message = f"Match status: {context.match_status}"
            priority = "low"

        payload = NotificationPayload(
            recipient=recipient,
            subject=subject,
            message=message,
            priority=priority,
            metadata=context.metadata,
        )

        return await self.email_connector.execute(payload)

    async def _flag_unmatched(self, context: ActionContext) -> ActionResult:
        """Flag email as unmatched."""
        # Update email record with flag
        from app.db.repositories.email_repository import EmailRepository
        from app.db.models.email import Email

        repo = EmailRepository(Email, self.session)
        email = await repo.get_by_id(context.email_id)

        if email:
            # Could add a custom field, for now just log
            logger.info(f"[FLAG] Email {context.email_id} flagged as unmatched")

            return ActionResult(
                action_type=ActionType.FLAG_UNMATCHED,
                status=ActionStatus.SUCCESS,
                outcome="email_flagged",
                message=f"Email {context.email_id} flagged as unmatched",
                metadata={"email_id": context.email_id},
            )
        else:
            return ActionResult(
                action_type=ActionType.FLAG_UNMATCHED,
                status=ActionStatus.FAILED,
                outcome="email_not_found",
                message=f"Email {context.email_id} not found",
            )

    async def _escalate(self, context: ActionContext) -> ActionResult:
        """Escalate match to senior operations."""
        recipient = (
            self.config.ESCALATION_EMAIL
            or self.config.OPERATIONS_EMAIL
            or "escalation@example.com"
        )

        # Build escalation details
        reasons = []
        if context.metadata.get("amount", 0) > (
            self.policy.escalate_if_amount_above or 0
        ):
            reasons.append(
                f"High amount: {context.metadata.get('amount')} {context.metadata.get('currency')}"
            )
        if (
            context.metadata.get("alternative_candidates_count", 0)
            >= self.policy.ambiguous_candidates_count
        ):
            reasons.append(
                f"Multiple matches: {context.metadata.get('alternative_candidates_count')} candidates"
            )
        if (
            not context.metadata.get("reference")
            or context.metadata.get("reference") == "N/A"
        ):
            reasons.append("Missing reference")

        payload = NotificationPayload(
            recipient=recipient,
            subject=f"🚨 ESCALATION - Match #{context.match_id}",
            message=(
                f"Match requires immediate attention:\n\n"
                f"Match ID: {context.match_id}\n"
                f"Confidence: {context.confidence:.2%}\n"
                f"Amount: {context.metadata.get('amount')} {context.metadata.get('currency')}\n\n"
                f"Escalation reasons:\n" + "\n".join(f"- {r}" for r in reasons) + "\n\n"
                f"View details: /matches/{context.match_id}"
            ),
            priority="urgent",
            metadata={"reasons": reasons, **context.metadata},
        )

        return await self.email_connector.execute(payload)

    async def _send_webhook(self, context: ActionContext) -> ActionResult:
        """Send webhook notification."""
        # Get webhook URL from config or metadata
        webhook_url = self.config.WEBHOOK_URLS.get("reconciliation")

        if not webhook_url:
            return ActionResult(
                action_type=ActionType.SEND_WEBHOOK,
                status=ActionStatus.SKIPPED,
                outcome="no_webhook_configured",
                message="No webhook URL configured",
            )

        payload = WebhookPayload(
            url=webhook_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body={
                "event": "match_completed",
                "match_id": context.match_id,
                "email_id": context.email_id,
                "transaction_id": context.transaction_id,
                "status": context.match_status,
                "confidence": context.confidence,
                "outcome": context.match_outcome.value,
                "metadata": context.metadata,
            },
        )

        return await self.webhook_connector.execute(payload)
