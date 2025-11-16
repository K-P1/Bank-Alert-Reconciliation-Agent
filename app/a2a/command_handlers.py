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

    async def reconcile_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate reconciliation.

        Params:
            limit (optional): Number of emails to process
            rematch (optional): Force re-matching of already matched emails
        """
        limit = params.get("limit")
        rematch = params.get("rematch", False)

        logger.info("handler.reconcile_now.start", limit=limit, rematch=rematch)

        try:
            # Run reconciliation
            batch_result = await match_unmatched(self.db, limit=limit)

            summary = (
                f"✅ Reconciliation complete!\n\n"
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
                "handler.reconcile_now.success",
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
            logger.exception("handler.reconcile_now.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Reconciliation failed: {str(exc)}",
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
        List unmatched emails.

        Params:
            limit (optional): Number of results to return (default: 10)
        """
        limit = params.get("limit", 10)

        logger.info("handler.list_unmatched.start", limit=limit)

        try:
            # Get matched email IDs
            matched_email_ids = await self.match_repo.get_matched_email_ids()

            # Build query for unmatched emails
            from sqlalchemy import select, desc

            query = select(self.email_repo.model)

            # Filter out matched emails
            if matched_email_ids:
                query = query.where(~self.email_repo.model.id.in_(matched_email_ids))

            # Order and limit
            query = query.order_by(desc(self.email_repo.model.created_at)).limit(limit)

            # Execute query
            result = await self.email_repo.session.execute(query)
            unmatched_emails = list(result.scalars().all())

            if not unmatched_emails:
                summary = "✅ Great! No unmatched emails found."
                artifacts: List[Dict[str, Any]] = []
            else:
                summary = f"📋 **Unmatched Emails** (Showing {len(unmatched_emails)} of {len(unmatched_emails)})\n\n"

                artifacts = []
                for email in unmatched_emails:
                    summary += f"  • Email #{email.id} - {email.sender} - ₦{email.amount:,.2f} ({email.parsed_at or email.received_at})\n"

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

            logger.info(
                "handler.list_unmatched.success", unmatched_count=len(unmatched_emails)
            )

            return {
                "status": "success",
                "summary": summary,
                "artifacts": artifacts,
                "meta": {"limit": limit, "count": len(unmatched_emails)},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler.list_unmatched.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to list unmatched emails: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_confidence_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate confidence and accuracy report.

        Params:
            days (optional): Number of days to analyze (default: 7)
        """
        days = params.get("days", 7)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info("handler.get_confidence_report.start", days=days)

        try:
            # Get all matches in the time period
            matches = await self.match_repo.filter(created_at__gte=since)

            if not matches:
                summary = f"📊 No matches found in the last {days} days."
                return {
                    "status": "success",
                    "summary": summary,
                    "artifacts": [],
                    "meta": {"days": days},
                }

            # Calculate statistics
            total_matches = len(matches)
            confidences = [m.confidence for m in matches if m.confidence is not None]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            high_confidence = len([c for c in confidences if c >= 0.8])
            medium_confidence = len([c for c in confidences if 0.5 <= c < 0.8])
            low_confidence = len([c for c in confidences if c < 0.5])

            summary = (
                f"📊 **Confidence Report** (Last {days} days)\n\n"
                f"**Overall:**\n"
                f"  • Total matches: {total_matches}\n"
                f"  • Average confidence: {avg_confidence:.2%}\n\n"
                f"**Distribution:**\n"
                f"  • High (≥80%): {high_confidence} ({high_confidence/total_matches*100:.1f}%)\n"
                f"  • Medium (50-80%): {medium_confidence} ({medium_confidence/total_matches*100:.1f}%)\n"
                f"  • Low (<50%): {low_confidence} ({low_confidence/total_matches*100:.1f}%)\n"
            )

            logger.info(
                "handler.get_confidence_report.success",
                total_matches=total_matches,
                avg_confidence=avg_confidence,
            )

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "confidence_report",
                        "data": {
                            "total_matches": total_matches,
                            "average_confidence": avg_confidence,
                            "distribution": {
                                "high": high_confidence,
                                "medium": medium_confidence,
                                "low": low_confidence,
                            },
                        },
                    }
                ],
                "meta": {"days": days, "since": since.isoformat()},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("handler.get_confidence_report.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to generate report: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def fetch_emails(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate email fetch from IMAP.

        Params:
            None
        """
        logger.info("handler.fetch_emails.start")

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

            logger.info("handler.fetch_emails.success", stored=result.emails_stored)

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
            logger.exception("handler.fetch_emails.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Email fetch failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_email_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get email fetcher status and metrics.

        Params:
            None
        """
        logger.info("handler.get_email_status.start")

        try:
            from app.emails.router import get_status

            result = await get_status()
            status = self._as_dict(result)
            status = self._as_dict(result)
            status = self._as_dict(result)

            # Some routers return Pydantic models while other helpers return
            # raw dicts. Normalize to a plain dict to make attribute access
            # predictable and satisfy static type checkers (Pylance).
            if isinstance(result, dict):
                status = result
            else:
                # Pydantic v2+ uses model_dump(), fall back to .dict()
                status = (
                    result.model_dump()
                    if hasattr(result, "model_dump")
                    else getattr(result, "dict", lambda: {})()
                )

            summary = (
                f"📧 **Email Fetcher Status**\n\n"
                f"**State:**\n"
                f"  • Running: {'Yes ✓' if status.get('running') else 'No ✗'}\n"
                f"  • Enabled: {'Yes' if status.get('enabled') else 'No'}\n\n"
                f"**Metrics:**\n"
                f"  • Total runs: {status.get('aggregate_metrics', {}).get('total_runs', 0)}\n"
                f"  • Successful: {status.get('aggregate_metrics', {}).get('successful_runs', 0)}\n"
                f"  • Failed: {status.get('aggregate_metrics', {}).get('failed_runs', 0)}\n"
            )

            last_run = status.get("last_run") or {}
            last_started = last_run.get("started_at")
            if last_started:
                summary += f"  • Last run: {last_started}\n"

            logger.info("handler.get_email_status.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "email_status",
                        "data": status,
                    }
                ],
                "meta": {"running": status.get("running", False)},
            }
        except Exception as exc:
            logger.exception("handler.get_email_status.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get email status: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def start_email_fetcher(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start the email fetcher background service.

        Params:
            None
        """
        logger.info("handler.start_email_fetcher.start")

        try:
            from app.emails.router import start_fetcher

            result = await start_fetcher()

            summary = f"✅ {result['message']}"

            logger.info("handler.start_email_fetcher.success")

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
            logger.exception("handler.start_email_fetcher.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to start email fetcher: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def stop_email_fetcher(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop the email fetcher background service.

        Params:
            None
        """
        logger.info("handler.stop_email_fetcher.start")

        try:
            from app.emails.router import stop_fetcher

            result = await stop_fetcher()

            summary = f"✅ {result['message']}"

            logger.info("handler.stop_email_fetcher.success")

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
            logger.exception("handler.stop_email_fetcher.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to stop email fetcher: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def poll_transactions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger immediate transaction polling from APIs.

        Params:
            None
        """
        logger.info("handler.poll_transactions.start")

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

            logger.info("handler.poll_transactions.success", run_id=result.run_id)

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
            logger.exception("handler.poll_transactions.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Transaction poll failed: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_transaction_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get transaction poller status and metrics.

        Params:
            None
        """
        logger.info("handler.get_transaction_status.start")

        try:
            from app.transactions.router import get_status

            result = await get_status()
            status = self._as_dict(result)

            summary = (
                f"💳 **Transaction Poller Status**\n\n"
                f"**State:**\n"
                f"  • Running: {'Yes ✓' if status.get('running') else 'No ✗'}\n"
                f"  • Enabled: {'Yes' if status.get('enabled') else 'No'}\n\n"
                f"**Circuit Breaker:**\n"
                f"  • State: {status.get('circuit_breaker', {}).get('state', 'unknown')}\n"
                f"  • Failures: {status.get('circuit_breaker', {}).get('failures', 0)}\n\n"
                f"**Metrics (24h):**\n"
                f"  • Total runs: {status.get('metrics_24h', {}).get('total_runs', 0)}\n"
                f"  • Successful: {status.get('metrics_24h', {}).get('successful_runs', 0)}\n"
                f"  • Failed: {status.get('metrics_24h', {}).get('failed_runs', 0)}\n"
            )

            logger.info("handler.get_transaction_status.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "transaction_status",
                        "data": status,
                    }
                ],
                "meta": {"running": status.get("running", False)},
            }
        except Exception as exc:
            logger.exception("handler.get_transaction_status.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get transaction status: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def start_transaction_poller(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start the transaction poller background service.

        Params:
            None
        """
        logger.info("handler.start_transaction_poller.start")

        try:
            from app.transactions.router import start_poller

            result = await start_poller()

            summary = f"✅ {result['message']}"

            logger.info("handler.start_transaction_poller.success")

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
            logger.exception("handler.start_transaction_poller.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to start transaction poller: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def stop_transaction_poller(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop the transaction poller background service.

        Params:
            None
        """
        logger.info("handler.stop_transaction_poller.start")

        try:
            from app.transactions.router import stop_poller

            result = await stop_poller()

            summary = f"✅ {result['message']}"

            logger.info("handler.stop_transaction_poller.success")

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
            logger.exception("handler.stop_transaction_poller.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to stop transaction poller: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_workflow_policy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current workflow policy configuration.

        Params:
            None
        """
        logger.info("handler.get_workflow_policy.start")

        try:
            from app.actions.router import get_workflow_policy

            result = await get_workflow_policy()
            status = self._as_dict(result)

            summary = (
                f"⚙️ **Workflow Policy Configuration**\n\n"
                f"**Actions for Matched Emails:**\n"
                f"  • {', '.join(result.matched_actions)}\n\n"
                f"**Actions for Ambiguous Matches:**\n"
                f"  • {', '.join(result.ambiguous_actions)}\n\n"
                f"**Actions for Unmatched Emails:**\n"
                f"  • {', '.join(result.unmatched_actions)}\n\n"
                f"**Actions for Review:**\n"
                f"  • {', '.join(result.review_actions)}\n\n"
                f"**Thresholds:**\n"
                f"  • High confidence: {result.high_confidence_threshold:.0%}\n"
                f"  • Low confidence: {result.low_confidence_threshold:.0%}\n"
            )

            logger.info("handler.get_workflow_policy.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "workflow_policy",
                        "data": status,
                    }
                ],
                "meta": status,
            }
        except Exception as exc:
            logger.exception("handler.get_workflow_policy.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get workflow policy: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_action_audits(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get action audit logs.

        Params:
            limit (optional): Number of results to return (default: 20)
            hours (optional): Filter by last N hours
        """
        limit = params.get("limit", 20)
        hours = params.get("hours")

        logger.info("handler.get_action_audits.start", limit=limit, hours=hours)

        try:
            from app.actions.router import get_action_audits

            result = await get_action_audits(since_hours=hours, limit=limit)

            if not result:
                summary = "✅ No action audits found."
                artifacts = []
            else:
                summary = f"📋 **Action Audit Logs** (Showing {len(result)})\n\n"

                for audit in result[:5]:  # Show first 5 in summary
                    summary += (
                        f"  • {audit.action_type} - {audit.status} "
                        f"({audit.started_at})\n"
                    )

                if len(result) > 5:
                    summary += f"\n  ... and {len(result) - 5} more\n"

                artifacts = [
                    {
                        "kind": "action_audits",
                        "data": [a.model_dump() for a in result],
                    }
                ]

            logger.info("handler.get_action_audits.success", count=len(result))

            return {
                "status": "success",
                "summary": summary,
                "artifacts": artifacts,
                "meta": {"limit": limit, "count": len(result)},
            }
        except Exception as exc:
            logger.exception("handler.get_action_audits.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get action audits: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_action_statistics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get action execution statistics.

        Params:
            hours (optional): Statistics for last N hours (default: 24)
        """
        hours = params.get("hours", 24)

        logger.info("handler.get_action_statistics.start", hours=hours)

        try:
            from app.actions.router import get_action_statistics

            result = await get_action_statistics(since_hours=hours)
            status = self._as_dict(result)

            summary = (
                f"📊 **Action Statistics** (Last {hours} hours)\n\n"
                f"**Overall:**\n"
                f"  • Total actions: {result.total}\n"
                f"  • Successful: {result.success}\n"
                f"  • Failed: {result.failed}\n"
                f"  • Pending: {result.pending}\n\n"
            )

            if result.by_type:
                summary += "**By Type:**\n"
                for action_type, count in result.by_type.items():
                    summary += f"  • {action_type}: {count}\n"

            logger.info("handler.get_action_statistics.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "action_statistics",
                        "data": status,
                    }
                ],
                "meta": {"hours": hours},
            }
        except Exception as exc:
            logger.exception("handler.get_action_statistics.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get action statistics: {str(exc)}",
                "artifacts": [],
                "meta": {"error": str(exc)},
            }

    async def get_automation_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get automation service status.

        Params:
            None
        """
        logger.info("handler.get_automation_status.start")

        try:
            from app.actions.automation_router import get_automation_status

            result = await get_automation_status()
            status = self._as_dict(result)

            summary = (
                f"🤖 **Automation Status**\n\n"
                f"**State:**\n"
                f"  • Running: {'Yes ✓' if status.get('running') else 'No ✗'}\n"
                f"  • Interval: {status.get('interval_seconds', 0)}s\n"
                f"  • Actions enabled: {'Yes' if status.get('actions_enabled') else 'No'}\n\n"
                f"**Metrics:**\n"
            )

            for key, value in result.metrics.items():
                summary += f"  • {key}: {value}\n"

            logger.info("handler.get_automation_status.success")

            return {
                "status": "success",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "automation_status",
                        "data": status,
                    }
                ],
                "meta": {"running": status.get("running", False)},
            }
        except Exception as exc:
            logger.exception("handler.get_automation_status.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Failed to get automation status: {str(exc)}",
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
            from app.actions.automation_router import (
                start_automation,
                StartAutomationRequest,
            )

            request = None
            if interval:
                request = StartAutomationRequest(
                    interval_seconds=interval, enable_actions=True
                )

            result = await start_automation(request)

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
            from app.actions.automation_router import stop_automation

            result = await stop_automation()

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

    async def run_automation_once(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single automation cycle manually.

        Params:
            None
        """
        logger.info("handler.run_automation_once.start")

        try:
            from app.actions.automation_router import run_reconciliation_once

            result = await run_reconciliation_once()

            summary = (
                f"{'✅' if result.success else '⚠️'} {result.message}\n\n"
                f"📊 **Cycle Statistics:**\n"
            )

            for key, value in result.stats.items():
                if isinstance(value, dict):
                    summary += f"\n**{key.replace('_', ' ').title()}:**\n"
                    for sub_key, sub_value in value.items():
                        summary += f"  • {sub_key}: {sub_value}\n"
                else:
                    summary += f"  • {key}: {value}\n"

            logger.info("handler.run_automation_once.success", success=result.success)

            return {
                "status": "success" if result.success else "partial",
                "summary": summary,
                "artifacts": [
                    {
                        "kind": "automation_cycle",
                        "data": result.stats,
                    }
                ],
                "meta": {"success": result.success},
            }
        except Exception as exc:
            logger.exception("handler.run_automation_once.error", error=str(exc))
            return {
                "status": "error",
                "summary": f"❌ Automation cycle failed: {str(exc)}",
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
