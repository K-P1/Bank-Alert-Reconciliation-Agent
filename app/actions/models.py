"""Models for post-processing actions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions that can be taken."""

    MARK_VERIFIED = "mark_verified"
    UPDATE_LEDGER = "update_ledger"
    NOTIFY_CRM = "notify_crm"
    SEND_WEBHOOK = "send_webhook"
    CREATE_TICKET = "create_ticket"
    SEND_EMAIL = "send_email"
    UPDATE_STATUS = "update_status"
    FLAG_UNMATCHED = "flag_unmatched"
    ESCALATE = "escalate"


class ActionStatus(str, Enum):
    """Status of action execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class MatchOutcome(str, Enum):
    """Outcome categories for match results."""

    MATCHED = "matched"  # High confidence auto-match
    AMBIGUOUS = "ambiguous"  # Multiple candidates or low confidence
    UNMATCHED = "unmatched"  # No candidates found
    REVIEW = "review"  # Needs manual review
    REJECTED = "rejected"  # Below threshold


class NotificationPayload(BaseModel):
    """Payload for notification actions."""

    recipient: str
    subject: str
    message: str
    priority: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketPayload(BaseModel):
    """Payload for ticket creation actions."""

    title: str
    description: str
    priority: str = "medium"
    category: str
    assigned_to: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebhookPayload(BaseModel):
    """Payload for webhook actions."""

    url: str
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any]
    retry_config: Optional[dict[str, Any]] = None


class ActionResult(BaseModel):
    """Result of an action execution."""

    action_type: ActionType
    status: ActionStatus
    outcome: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None
    retry_count: int = 0


class ActionContext(BaseModel):
    """Context for action execution."""

    match_id: int
    email_id: int
    transaction_id: Optional[int] = None
    match_status: str
    confidence: float
    match_outcome: MatchOutcome
    actor: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowPolicy(BaseModel):
    """Policy for determining which actions to take."""

    # Matched outcomes
    matched_actions: list[ActionType] = Field(
        default_factory=lambda: [
            ActionType.MARK_VERIFIED,
            ActionType.UPDATE_STATUS,
            ActionType.NOTIFY_CRM,
        ]
    )

    # Ambiguous outcomes (multiple candidates or low confidence)
    ambiguous_actions: list[ActionType] = Field(
        default_factory=lambda: [
            ActionType.CREATE_TICKET,
            ActionType.SEND_EMAIL,
            ActionType.ESCALATE,
        ]
    )

    # Unmatched outcomes
    unmatched_actions: list[ActionType] = Field(
        default_factory=lambda: [
            ActionType.FLAG_UNMATCHED,
            ActionType.CREATE_TICKET,
            ActionType.SEND_EMAIL,
        ]
    )

    # Review outcomes
    review_actions: list[ActionType] = Field(
        default_factory=lambda: [
            ActionType.CREATE_TICKET,
            ActionType.SEND_EMAIL,
        ]
    )

    # Thresholds
    high_confidence_threshold: float = 0.85
    low_confidence_threshold: float = 0.50
    ambiguous_candidates_count: int = 2

    # Escalation rules
    escalate_if_amount_above: Optional[float] = 1_000_000.0  # NGN 1M
    escalate_if_multiple_matches: bool = True
    escalate_if_no_reference: bool = True

    def get_actions_for_outcome(self, outcome: MatchOutcome) -> list[ActionType]:
        """Get list of actions for a given outcome."""
        if outcome == MatchOutcome.MATCHED:
            return self.matched_actions
        elif outcome == MatchOutcome.AMBIGUOUS:
            return self.ambiguous_actions
        elif outcome == MatchOutcome.UNMATCHED:
            return self.unmatched_actions
        elif outcome == MatchOutcome.REVIEW:
            return self.review_actions
        else:
            return []

    def should_escalate(self, context: ActionContext) -> bool:
        """Determine if a match should be escalated."""
        # Check amount threshold
        amount = context.metadata.get("amount", 0)
        if self.escalate_if_amount_above and amount > self.escalate_if_amount_above:
            return True

        # Check multiple matches
        if self.escalate_if_multiple_matches:
            alternative_count = context.metadata.get("alternative_candidates_count", 0)
            if alternative_count >= self.ambiguous_candidates_count:
                return True

        # Check missing reference
        if self.escalate_if_no_reference:
            reference = context.metadata.get("reference")
            if not reference or reference == "N/A":
                return True

        return False
