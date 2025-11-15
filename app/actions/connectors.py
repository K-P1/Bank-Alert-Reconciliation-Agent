"""Connectors for downstream systems."""

from __future__ import annotations

import logging
import httpx
from abc import ABC, abstractmethod
from typing import Any

from app.actions.config import get_actions_config
from app.actions.models import (
    ActionResult,
    ActionStatus,
    ActionType,
    NotificationPayload,
    TicketPayload,
    WebhookPayload,
)

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Base class for all connectors."""

    def __init__(self):
        self.config = get_actions_config()

    @abstractmethod
    async def execute(self, payload: Any) -> ActionResult:
        """Execute the connector action."""
        pass


class WebhookConnector(BaseConnector):
    """Connector for sending webhooks to external systems."""

    async def execute(self, payload: WebhookPayload) -> ActionResult:
        """Send webhook to configured URL."""
        try:
            async with httpx.AsyncClient(
                timeout=self.config.WEBHOOK_TIMEOUT_SECONDS
            ) as client:
                response = await client.request(
                    method=payload.method,
                    url=payload.url,
                    headers=payload.headers,
                    json=payload.body,
                )

                if response.status_code < 400:
                    return ActionResult(
                        action_type=ActionType.SEND_WEBHOOK,
                        status=ActionStatus.SUCCESS,
                        outcome="webhook_sent",
                        message=f"Webhook sent successfully to {payload.url}",
                        metadata={
                            "url": payload.url,
                            "status_code": response.status_code,
                            "response_body": response.text[:500],
                        },
                    )
                else:
                    return ActionResult(
                        action_type=ActionType.SEND_WEBHOOK,
                        status=ActionStatus.FAILED,
                        outcome="webhook_failed",
                        message=f"Webhook failed with status {response.status_code}",
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        metadata={
                            "url": payload.url,
                            "status_code": response.status_code,
                        },
                    )

        except Exception as e:
            logger.error(f"Webhook execution failed: {e}", exc_info=True)
            return ActionResult(
                action_type=ActionType.SEND_WEBHOOK,
                status=ActionStatus.FAILED,
                outcome="webhook_error",
                message="Webhook execution failed",
                error=str(e),
                metadata={"url": payload.url},
            )


class DatabaseConnector(BaseConnector):
    """Connector for database updates (transaction verification)."""

    async def execute(self, transaction_id: int, session: Any) -> ActionResult:
        """Mark transaction as verified in database."""
        try:
            from datetime import datetime, timezone
            from app.db.repositories.transaction_repository import TransactionRepository
            from app.db.models.transaction import Transaction

            repo = TransactionRepository(Transaction, session)
            txn = await repo.get_by_id(transaction_id)

            if not txn:
                return ActionResult(
                    action_type=ActionType.MARK_VERIFIED,
                    status=ActionStatus.FAILED,
                    outcome="transaction_not_found",
                    message=f"Transaction {transaction_id} not found",
                    error="Transaction does not exist",
                )

            # Update verification status
            txn.is_verified = True
            txn.verified_at = datetime.now(timezone.utc)
            txn.status = "verified"

            await session.commit()

            return ActionResult(
                action_type=ActionType.MARK_VERIFIED,
                status=ActionStatus.SUCCESS,
                outcome="transaction_verified",
                message=f"Transaction {transaction_id} marked as verified",
                metadata={
                    "transaction_id": transaction_id,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                },
            )

        except Exception as e:
            logger.error(f"Database update failed: {e}", exc_info=True)
            await session.rollback()
            return ActionResult(
                action_type=ActionType.MARK_VERIFIED,
                status=ActionStatus.FAILED,
                outcome="database_error",
                message="Failed to update transaction",
                error=str(e),
            )


class EmailNotificationConnector(BaseConnector):
    """Connector for sending email notifications."""

    async def execute(self, payload: NotificationPayload) -> ActionResult:
        """Send email notification."""
        try:
            # Check if SMTP is configured
            if not self.config.SMTP_HOST or not self.config.SMTP_USER:
                logger.warning("SMTP not configured, simulating email send")
                return ActionResult(
                    action_type=ActionType.SEND_EMAIL,
                    status=ActionStatus.SUCCESS,
                    outcome="email_simulated",
                    message=f"Email simulated (SMTP not configured): {payload.subject}",
                    metadata={
                        "recipient": payload.recipient,
                        "subject": payload.subject,
                        "note": "SMTP not configured, email was not actually sent",
                    },
                )

            # TODO: Implement actual SMTP sending
            # For now, return success with simulation
            logger.info(f"Email notification: {payload.recipient} | {payload.subject}")

            return ActionResult(
                action_type=ActionType.SEND_EMAIL,
                status=ActionStatus.SUCCESS,
                outcome="email_sent",
                message=f"Email sent to {payload.recipient}",
                metadata={
                    "recipient": payload.recipient,
                    "subject": payload.subject,
                    "priority": payload.priority,
                },
            )

        except Exception as e:
            logger.error(f"Email send failed: {e}", exc_info=True)
            return ActionResult(
                action_type=ActionType.SEND_EMAIL,
                status=ActionStatus.FAILED,
                outcome="email_error",
                message="Failed to send email",
                error=str(e),
            )


class TicketConnector(BaseConnector):
    """Connector for creating tickets in ticketing systems."""

    async def execute(self, payload: TicketPayload) -> ActionResult:
        """Create ticket in ticketing system."""
        try:
            # Check if ticket system is configured
            if not self.config.TICKET_SYSTEM_URL:
                logger.warning(
                    "Ticket system not configured, simulating ticket creation"
                )
                return ActionResult(
                    action_type=ActionType.CREATE_TICKET,
                    status=ActionStatus.SUCCESS,
                    outcome="ticket_simulated",
                    message=f"Ticket simulated: {payload.title}",
                    metadata={
                        "title": payload.title,
                        "priority": payload.priority,
                        "category": payload.category,
                        "note": "Ticket system not configured, ticket was not actually created",
                    },
                )

            # TODO: Implement actual ticket system integration
            # For now, simulate ticket creation
            ticket_id = f"TKT-{abs(hash(payload.title)) % 100000}"

            logger.info(f"Ticket created: {ticket_id} | {payload.title}")

            return ActionResult(
                action_type=ActionType.CREATE_TICKET,
                status=ActionStatus.SUCCESS,
                outcome="ticket_created",
                message=f"Ticket {ticket_id} created",
                metadata={
                    "ticket_id": ticket_id,
                    "title": payload.title,
                    "priority": payload.priority,
                    "category": payload.category,
                },
            )

        except Exception as e:
            logger.error(f"Ticket creation failed: {e}", exc_info=True)
            return ActionResult(
                action_type=ActionType.CREATE_TICKET,
                status=ActionStatus.FAILED,
                outcome="ticket_error",
                message="Failed to create ticket",
                error=str(e),
            )


class CRMConnector(BaseConnector):
    """Connector for CRM system notifications."""

    async def execute(self, data: dict[str, Any]) -> ActionResult:
        """Send notification to CRM system."""
        try:
            if not self.config.CRM_API_URL:
                logger.warning("CRM not configured, simulating notification")
                return ActionResult(
                    action_type=ActionType.NOTIFY_CRM,
                    status=ActionStatus.SUCCESS,
                    outcome="crm_simulated",
                    message="CRM notification simulated",
                    metadata={
                        "data": data,
                        "note": "CRM not configured, notification was not actually sent",
                    },
                )

            # Send to CRM API
            async with httpx.AsyncClient(
                timeout=self.config.WEBHOOK_TIMEOUT_SECONDS
            ) as client:
                headers = {"Authorization": f"Bearer {self.config.CRM_API_KEY}"}
                response = await client.post(
                    self.config.CRM_API_URL,
                    headers=headers,
                    json=data,
                )

                if response.status_code < 400:
                    return ActionResult(
                        action_type=ActionType.NOTIFY_CRM,
                        status=ActionStatus.SUCCESS,
                        outcome="crm_notified",
                        message="CRM notification sent successfully",
                        metadata={"status_code": response.status_code},
                    )
                else:
                    return ActionResult(
                        action_type=ActionType.NOTIFY_CRM,
                        status=ActionStatus.FAILED,
                        outcome="crm_failed",
                        message=f"CRM notification failed with status {response.status_code}",
                        error=response.text[:200],
                    )

        except Exception as e:
            logger.error(f"CRM notification failed: {e}", exc_info=True)
            return ActionResult(
                action_type=ActionType.NOTIFY_CRM,
                status=ActionStatus.FAILED,
                outcome="crm_error",
                message="Failed to notify CRM",
                error=str(e),
            )
