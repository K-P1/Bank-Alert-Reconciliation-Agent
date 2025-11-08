"""
Command handlers for natural language commands in the A2A endpoint.

Each handler implements a specific user action that can be triggered via
plain text messages from Telex.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.match_repository import MatchRepository
from app.db.repositories.transaction_repository import TransactionRepository
from app.db.models.email import Email
from app.db.models.match import Match
from app.db.models.transaction import Transaction
from app.matching.engine import match_unmatched, MatchingEngine
from app.matching.models import BatchMatchResult


logger = structlog.get_logger("a2a.handlers")


class CommandHandlers:
    """Collection of command handler functions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_repo = EmailRepository(Email, db)
        self.match_repo = MatchRepository(Match, db)
        self.transaction_repo = TransactionRepository(Transaction, db)

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
                artifacts = []
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
