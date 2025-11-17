"""
Command handlers for natural language commands in the A2A endpoint.

Each handler implements a specific user action that can be triggered via
plain text messages from Telex.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.match_repository import MatchRepository
from app.db.repositories.transaction_repository import TransactionRepository
from app.db.models.email import Email
from app.db.models.match import Match
from app.db.models.transaction import Transaction
from app.matching.engine import match_unmatched
from app.matching.models import BatchMatchResult


logger = structlog.get_logger("a2a.handlers")


class CommandHandlers:
    """Collection of command handler functions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_repo = EmailRepository(Email, db)
        self.match_repo = MatchRepository(Match, db)
        self.transaction_repo = TransactionRepository(Transaction, db)

    def _as_dict(self, obj: Any) -> Dict[str, Any]:
        """Normalize a Pydantic model or mapping to a plain dict.

        This helps static type checkers and ensures consistent handling
        of router responses that may return either a Pydantic model
        or a raw dict.
        """
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            # model_dump returns a variety of types; cast to a dict for
            # the static type checker to accept our usage below.
            return cast(Dict[str, Any], obj.model_dump())
        if hasattr(obj, "dict"):
            return cast(Dict[str, Any], obj.dict())
        return {}

    async def match_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate matching of unmatched emails.

        Params:
            limit (optional): Number of emails to process
            rematch (optional): Force re-matching of already matched emails
        """
        limit = params.get("limit")
        rematch = params.get("rematch", False)

        logger.info("handler.match_now.start", limit=limit, rematch=rematch)

        try:
            # Run reconciliation
            batch_result = await match_unmatched(self.db, limit=limit)

            summary = (
                f"✅ Matching complete!\n\n"
                f"📊 **Results:**\n"
                f"  • Total processed: {batch_result.total_emails}\n"
                f"  • Auto-matched: {batch_result.total_matched}\n"
                f"  • Needs review: {batch_result.total_needs_review}\n"
                f"  • Rejected: {batch_result.total_rejected}\n"
                f"  • No candidates: {batch_result.total_no_candidates}\n"
                f"  • Avg confidence: {batch_result.average_confidence:.2%}\n"
            )

            # Build artifact list
            artifacts = self._build_reconciliation_artifacts(batch_result)

            logger.info(
                "handler.match_now.success",
                total=batch_result.total_emails,
                matched=batch_result.total_matched,
            )

            return {
                "status": "success",
                "summary": summary,
                "artifacts": artifacts,
                "meta": {
                    "batch": batch_result.get_summary(),
                    "params": {"limit": limit, "rematch": rematch},
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler.match_now.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Matching failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def show_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Show summary of current reconciliation state.

        Params:
            days (optional): Number of days to look back (default: 7)
        """
        days = params.get("days", 7)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info("handler.show_summary.start", days=days)

        try:
            # Get counts from database
            total_emails = await self.email_repo.count(created_at__gte=since)
            total_transactions = await self.transaction_repo.count(
                created_at__gte=since
            )
            total_matches = await self.match_repo.count(created_at__gte=since)

            # Get match status breakdown
            matched_count = await self.match_repo.count(
                status="matched", created_at__gte=since
            )
            needs_review_count = await self.match_repo.count(
                status="review", created_at__gte=since
            )
            rejected_count = await self.match_repo.count(
                status="rejected", created_at__gte=since
            )
            no_candidates_count = await self.match_repo.count(
                status="no_candidates", created_at__gte=since
            )

            unmatched_emails = total_emails - total_matches

            summary = (
                f"📊 **Reconciliation Summary** (Last {days} days)\n\n"
                f"**Emails:**\n"
                f"  • Total: {total_emails}\n"
                f"  • Matched: {total_matches}\n"
                f"  • Unmatched: {unmatched_emails}\n\n"
                f"**Transactions:**\n"
                f"  • Total: {total_transactions}\n\n"
                f"**Match Status:**\n"
                f"  • Auto-matched: {matched_count}\n"
                f"  • Needs review: {needs_review_count}\n"
                f"  • Rejected: {rejected_count}\n"
                f"  • No candidates: {no_candidates_count}\n"
            )

            logger.info(
                "handler.show_summary.success",
                total_emails=total_emails,
                total_matches=total_matches,
            )

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "summary_stats",
                        "data": {
                            "emails": {
                                "total": total_emails,
                                "matched": total_matches,
                                "unmatched": unmatched_emails,
                            },
                            "transactions": {"total": total_transactions},
                            "matches": {
                                "auto_matched": matched_count,
                                "needs_review": needs_review_count,
                                "rejected": rejected_count,
                                "no_candidates": no_candidates_count,
                            },
                        },
                    }
                ],
                "meta": {"days": days, "since": since.isoformat()},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler.show_summary.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to retrieve summary: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def list_unmatched(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List unmatched emails and transactions.

        Params:
            limit (optional): Number of results to return per category (default: 10)
        """
        limit = params.get("limit", 10)

        logger.info("handler.list_unmatched.start", limit=limit)

        try:
            # Get matched email IDs and transaction IDs
            matched_email_ids = await self.match_repo.get_matched_email_ids()
            matched_transaction_ids = await self.match_repo.get_matched_transaction_ids()

            # Build query for unmatched emails
            from sqlalchemy import select, desc

            email_query = select(self.email_repo.model)

            # Filter out matched emails
            if matched_email_ids:
                email_query = email_query.where(~self.email_repo.model.id.in_(matched_email_ids))

            # Order and limit
            email_query = email_query.order_by(desc(self.email_repo.model.created_at)).limit(limit)

            # Execute email query
            email_result = await self.email_repo.session.execute(email_query)
            unmatched_emails = list(email_result.scalars().all())

            # Build query for unmatched transactions
            transaction_query = select(self.transaction_repo.model)

            # Filter out matched transactions
            if matched_transaction_ids:
                transaction_query = transaction_query.where(
                    ~self.transaction_repo.model.id.in_(matched_transaction_ids)
                )

            # Order and limit
            transaction_query = transaction_query.order_by(
                desc(self.transaction_repo.model.created_at)
            ).limit(limit)

            # Execute transaction query
            transaction_result = await self.transaction_repo.session.execute(transaction_query)
            unmatched_transactions = list(transaction_result.scalars().all())

            # Build summary and artifacts
            if not unmatched_emails and not unmatched_transactions:
                summary = "✅ Great! No unmatched emails or transactions found."
                artifacts: List[Dict[str, Any]] = []
            else:
                summary = f"📋 **Unmatched Items**\n\n"

                # Add email summary
                if unmatched_emails:
                    summary += f"**Emails** (Showing {len(unmatched_emails)})\n"
                    for email in unmatched_emails:
                        summary += f"  • Email #{email.id} - {email.sender} - ₦{email.amount:,.2f} ({email.parsed_at or email.received_at})\n"
                    summary += "\n"
                else:
                    summary += "**Emails**: None\n\n"

                # Add transaction summary
                if unmatched_transactions:
                    summary += f"**Transactions** (Showing {len(unmatched_transactions)})\n"
                    for txn in unmatched_transactions:
                        summary += f"  • Transaction #{txn.id} - {txn.reference or 'N/A'} - {txn.currency}{txn.amount:,.2f} ({txn.transaction_timestamp})\n"
                else:
                    summary += "**Transactions**: None\n"

                # Build artifacts
                artifacts = []
                for email in unmatched_emails:
                    artifacts.append(
                        {
                            "kind": "unmatched_email",
                            "data": {
                                "email_id": email.id,
                                "sender": email.sender,
                                "subject": email.subject,
                                "amount": float(email.amount) if email.amount else None,
                                "currency": email.currency,
                                "reference": email.reference,
                                "received_at": (
                                    email.received_at.isoformat()
                                    if email.received_at
                                    else None
                                ),
                            },
                        }
                    )

                for txn in unmatched_transactions:
                    artifacts.append(
                        {
                            "kind": "unmatched_transaction",
                            "data": {
                                "transaction_id": txn.id,
                                "reference": txn.reference,
                                "amount": float(txn.amount) if txn.amount else None,
                                "currency": txn.currency,
                                "description": txn.description,
                                "transaction_timestamp": (
                                    txn.transaction_timestamp.isoformat()
                                    if txn.transaction_timestamp
                                    else None
                                ),
                                "external_source": txn.external_source,
                            },
                        }
                    )

            logger.info(
                "handler.list_unmatched.success",
                unmatched_emails_count=len(unmatched_emails),
                unmatched_transactions_count=len(unmatched_transactions),
            )

            return {
                "status": "success",
                "summary": summary,
                "artifacts": artifacts,
                "meta": {
                    "limit": limit,
                    "email_count": len(unmatched_emails),
                    "transaction_count": len(unmatched_transactions),
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler.list_unmatched.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to list unmatched items: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def fetch_emails_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate email fetch from IMAP.

        Params:
            None
        """
        logger.info("handler.fetch_emails_now.start")

        try:
            # Import here to avoid circular dependency
            from app.emails.router import trigger_fetch

            result = await trigger_fetch()

            summary = (
                f"✅ Email fetch complete!\n\n"
                f"📊 **Results:**\n"
                f"  • Emails fetched: {result.emails_fetched}\n"
                f"  • Emails processed: {result.emails_processed}\n"
                f"  • Emails stored: {result.emails_stored}\n"
            )

            if result.error:
                summary += f"\n⚠️ {result.error}"

            logger.info("handler.fetch_emails_now.success", stored=result.emails_stored)

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "fetch_result",
                        "data": {
                            "run_id": result.run_id,
                            "emails_fetched": result.emails_fetched,
                            "emails_processed": result.emails_processed,
                            "emails_stored": result.emails_stored,
                        },
                    }
                ],
                "meta": {"run_id": result.run_id},
            }
        except Exception as exc:
            logger.exception("handler.fetch_emails_now.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Email fetch failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def fetch_transactions_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate transaction polling from APIs.

        Params:
            None
        """
        logger.info("handler.fetch_transactions_now.start")

        try:
            from app.transactions.router import trigger_poll

            result = await trigger_poll()

            summary = (
                f"✅ Transaction poll complete!\n\n"
                f"📊 **Results:**\n"
                f"  • Run ID: {result.run_id}\n"
                f"  • Status: {result.status}\n"
                f"  • Message: {result.message}\n"
            )

            if "warning" in result.details:
                summary += f"\n⚠️ {result.details['warning']}"

            logger.info("handler.fetch_transactions_now.success", run_id=result.run_id)

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "poll_result",
                        "data": result.details,
                    }
                ],
                "meta": {"run_id": result.run_id},
            }
        except Exception as exc:
            logger.exception("handler.fetch_transactions_now.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Transaction poll failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get system status and automation state.

        Params:
            None
        """
        logger.info("handler.get_status.start")

        try:
            from app.core.automation import get_automation_service

            automation = get_automation_service()
            status = automation.get_status()

            summary = (
                f"🤖 **System Status**\n\n"
                f"**Automation:**\n"
                f"  • Running: {'Yes ✓' if status['running'] else 'No ✗'}\n"
                f"  • Interval: {status['interval_seconds']}s\n"
                f"  • Total cycles: {status['total_cycles']}\n"
                f"  • Successful: {status['successful_cycles']}\n"
                f"  • Failed: {status['failed_cycles']}\n"
                f"  • Success rate: {status['success_rate']:.1f}%\n"
            )

            if status["last_run"]:
                summary += f"  • Last run: {status['last_run']}\n"

            if status["last_error"]:
                summary += f"\n⚠️ Last error: {status['last_error']}\n"

            logger.info("handler.get_status.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "system_status",
                        "data": status,
                    }
                ],
                "meta": {"running": status["running"]},
            }
        except Exception as exc:
            logger.exception("handler.get_status.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get status: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def start_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start the automation background service.

        Params:
            interval (optional): Override interval in seconds
        """
        interval = params.get("interval")

        logger.info("handler.start_automation.start", interval=interval)

        try:
            from app.core.automation import get_automation_service

            automation = get_automation_service()
            result = await automation.start(interval_seconds=interval)

            summary = f"✅ {result['message']}"

            logger.info("handler.start_automation.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "service_control",
                        "data": result,
                    }
                ],
                "meta": result,
            }
        except Exception as exc:
            logger.exception("handler.start_automation.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to start automation: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def stop_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop the automation background service.

        Params:
            None
        """
        logger.info("handler.stop_automation.start")

        try:
            from app.core.automation import get_automation_service

            automation = get_automation_service()
            result = await automation.stop()

            summary = f"✅ {result['message']}"

            logger.info("handler.stop_automation.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "service_control",
                        "data": result,
                    }
                ],
                "meta": result,
            }
        except Exception as exc:
            logger.exception("handler.stop_automation.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to stop automation: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def show_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Show system metrics and performance statistics.

        Params:
            hours (optional): Number of hours to look back (default: 24)
        """
        hours = params.get("hours", 24)

        logger.info("handler.show_metrics.start", hours=hours)

        try:
            summary = (
                f"📊 **System Metrics** (Last {hours} hours)\n\n"
                f"⚠️ Detailed metrics implementation pending.\n"
                f"This command will show:\n"
                f"  • Matching performance statistics\n"
                f"  • Email/transaction processing rates\n"
                f"  • System resource utilization\n"
                f"  • Error rates and trends\n"
            )

            logger.info("handler.show_metrics.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "metrics_placeholder",
                        "data": {"hours": hours, "status": "pending_implementation"},
                    }
                ],
                "meta": {"hours": hours},
            }
        except Exception as exc:
            logger.exception("handler.show_metrics.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to retrieve metrics: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def show_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Show recent system logs.

        Params:
            limit (optional): Number of log entries to return (default: 50)
            level (optional): Filter by log level (info, warning, error)
        """
        limit = params.get("limit", 50)
        level = params.get("level", "all")

        logger.info("handler.show_logs.start", limit=limit, level=level)

        try:
            summary = (
                f"📋 **System Logs** (Last {limit} entries)\n\n"
                f"⚠️ Log retrieval implementation pending.\n"
                f"This command will show:\n"
                f"  • Recent system events\n"
                f"  • Error messages and warnings\n"
                f"  • Filtering by log level: {level}\n"
                f"  • Timestamp and context information\n"
            )

            logger.info("handler.show_logs.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "logs_placeholder",
                        "data": {
                            "limit": limit,
                            "level": level,
                            "status": "pending_implementation",
                        },
                    }
                ],
                "meta": {"limit": limit, "level": level},
            }
        except Exception as exc:
            logger.exception("handler.show_logs.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to retrieve logs: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def manual_match(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manually match a specific email to a transaction.

        Params:
            email_id (required): Email ID to match
            transaction_id (required): Transaction ID to match
            confidence (optional): Manual confidence score (0.0-1.0)
        """
        email_id = params.get("email_id")
        transaction_id = params.get("transaction_id")
        confidence = params.get("confidence", 1.0)

        logger.info(
            "handler.manual_match.start",
            email_id=email_id,
            transaction_id=transaction_id,
            confidence=confidence,
        )

        try:
            if not email_id or not transaction_id:
                return {
                    "status": "error",
                    "summary": "❌ Both email_id and transaction_id are required for manual matching.",
                    "artifacts": [],
                    "meta": {"error": "missing_parameters"},
                }

            summary = (
                f"🔗 **Manual Match**\n\n"
                f"⚠️ Manual matching implementation pending.\n"
                f"This command will:\n"
                f"  • Match Email #{email_id} with Transaction #{transaction_id}\n"
                f"  • Set confidence score: {confidence:.2%}\n"
                f"  • Mark as manually reviewed\n"
                f"  • Create audit trail\n"
            )

            logger.info("handler.manual_match.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "manual_match_placeholder",
                        "data": {
                            "email_id": email_id,
                            "transaction_id": transaction_id,
                            "confidence": confidence,
                            "status": "pending_implementation",
                        },
                    }
                ],
                "meta": {"email_id": email_id, "transaction_id": transaction_id},
            }
        except Exception as exc:
            logger.exception("handler.manual_match.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Manual match failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    def _build_reconciliation_artifacts(
        self, batch_result: BatchMatchResult
    ) -> List[Dict[str, Any]]:
        """Build artifacts list from batch result."""
        artifacts = []
        for r in batch_result.results:
            artifact = {
                "kind": "reconciliation_result",
                "data": {
                    "email_id": r.email_id,
                    "email_message_id": r.email_message_id,
                    "matched": r.matched,
                    "confidence": r.confidence,
                    "status": r.match_status,
                    "best_candidate": (
                        {
                            "transaction_id": r.best_candidate.transaction_id,
                            "external_transaction_id": r.best_candidate.external_transaction_id,
                            "score": r.best_candidate.total_score,
                            "rule_scores": [
                                {
                                    "rule": rs.rule_name,
                                    "score": rs.score,
                                    "weight": rs.weight,
                                    "weighted": rs.weighted_score,
                                    "details": rs.details,
                                }
                                for rs in r.best_candidate.rule_scores
                            ],
                        }
                        if r.best_candidate
                        else None
                    ),
                    "alternatives": [
                        {
                            "transaction_id": c.transaction_id,
                            "external_transaction_id": c.external_transaction_id,
                            "score": c.total_score,
                            "rank": c.rank,
                        }
                        for c in r.alternative_candidates
                    ],
                    "notes": r.notes,
                },
            }
            artifacts.append(artifact)
        return artifacts


# Parameter extractors for command interpretation
def extract_limit(message: str, match: Optional[re.Match]) -> Optional[int]:
    """Extract limit parameter from message (e.g., 'reconcile 50 emails')."""
    number_pattern = re.compile(r"\b(\d+)\b")
    numbers = number_pattern.findall(message)
    if numbers:
        return int(numbers[0])
    return None


def extract_days(message: str, match: Optional[re.Match]) -> int:
    """Extract days parameter from message (e.g., 'last 7 days')."""
    number_pattern = re.compile(r"\b(\d+)\s*days?\b", re.IGNORECASE)
    match = number_pattern.search(message)
    if match:
        return int(match.group(1))
    return 7  # Default to 7 days


def extract_rematch_flag(message: str, match: Optional[re.Match]) -> bool:
    """Detect if rematch/rerun is requested."""
    rematch_pattern = re.compile(r"\b(re-?match|re-?run|force)\b", re.IGNORECASE)
    return bool(rematch_pattern.search(message))


def extract_hours(message: str, match: Optional[re.Match]) -> Optional[int]:
    """Extract hours parameter from message (e.g., 'last 24 hours')."""
    hours_pattern = re.compile(r"\b(\d+)\s*hours?\b", re.IGNORECASE)
    match_obj = hours_pattern.search(message)
    if match_obj:
        return int(match_obj.group(1))
    return None


def extract_action_type(message: str, match: Optional[re.Match]) -> Optional[str]:
    """Extract action type from message."""
    # Look for known action types
    action_types = ["email", "webhook", "log", "slack", "notification"]
    message_lower = message.lower()
    for action in action_types:
        if action in message_lower:
            return action
    return None


def extract_interval(message: str, match: Optional[re.Match]) -> Optional[int]:
    """Extract interval in seconds from message (e.g., '5 minutes', '300 seconds')."""
    # Try seconds first
    seconds_pattern = re.compile(r"\b(\d+)\s*(?:seconds?|secs?|s)\b", re.IGNORECASE)
    match_obj = seconds_pattern.search(message)
    if match_obj:
        return int(match_obj.group(1))

    # Try minutes
    minutes_pattern = re.compile(r"\b(\d+)\s*(?:minutes?|mins?|m)\b", re.IGNORECASE)
    match_obj = minutes_pattern.search(message)
    if match_obj:
        return int(match_obj.group(1)) * 60

    # Try hours
    hours_pattern = re.compile(r"\b(\d+)\s*(?:hours?|hrs?|h)\b", re.IGNORECASE)
    match_obj = hours_pattern.search(message)
    if match_obj:
        return int(match_obj.group(1)) * 3600

    return None
