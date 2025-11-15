"""Main matching engine that orchestrates the reconciliation process."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.email import Email
from app.db.models.match import Match
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.match_repository import MatchRepository
from app.matching.config import MatchingConfig
from app.matching.models import MatchResult, BatchMatchResult
from app.matching.retrieval import CandidateRetriever
from app.matching.scorer import MatchScorer
from app.normalization.models import NormalizedEmail
from app.normalization.normalizer import normalize_email

if TYPE_CHECKING:
    from app.emails.models import ParsedEmail

logger = logging.getLogger(__name__)


class MatchingEngine:
    """
    Main matching engine for transaction reconciliation.

    Orchestrates:
    1. Candidate retrieval
    2. Rule-based scoring
    3. Ranking and selection
    4. Result persistence
    """

    def __init__(
        self,
        session: AsyncSession,
        config: MatchingConfig | None = None,
        enable_actions: bool = True,
    ):
        """
        Initialize matching engine.

        Args:
            session: Database session
            config: Matching configuration
            enable_actions: Whether to enable post-processing actions
        """
        self.session = session
        self.config = config or MatchingConfig()
        self.config.validate_config()
        self.enable_actions = enable_actions

        # Initialize components
        self.retriever = CandidateRetriever(session, config)
        self.scorer = MatchScorer(config)

        # Initialize repositories
        from app.db.models.match import Match
        from app.db.models.transaction import Transaction
        from app.db.repositories.transaction_repository import TransactionRepository

        self.email_repo = EmailRepository(Email, self.session)
        self.match_repo = MatchRepository(Match, self.session)
        self.transaction_repo = TransactionRepository(Transaction, self.session)

        # Initialize action executor (lazy loading)
        self._action_executor = None

        logger.info(
            f"Matching engine initialized successfully "
            f"(actions: {'enabled' if enable_actions else 'disabled'})"
        )

    async def match_email(
        self,
        email: NormalizedEmail | ParsedEmail,
        email_db_id: int | None = None,
        persist: bool = True,
    ) -> MatchResult:
        """
        Match a single email to transactions.

        Args:
            email: Email to match (normalized or parsed)
            email_db_id: Database ID of email (required if persist=True)
            persist: Whether to persist results to database

        Returns:
            Match result
        """
        # Normalize if needed
        if not isinstance(email, NormalizedEmail):
            logger.info(f"[MATCH] Normalizing email: {email.message_id}")
            from app.emails.models import ParsedEmail as PE

            if isinstance(email, PE):
                normalized_email = normalize_email(email)
            else:
                raise ValueError(f"Unsupported email type: {type(email)}")
        else:
            normalized_email = email

        logger.info(
            f"[MATCH] Starting match process for email: {normalized_email.message_id} | "
            f"Amount: {normalized_email.amount} {normalized_email.currency} | "
            f"Reference: {normalized_email.reference.original if normalized_email.reference else 'None'}"
        )

        # Step 1: Retrieve candidates
        logger.info("[MATCH] Step 1: Retrieving candidate transactions...")
        candidates_txn = await self.retriever.get_candidates_for_email(normalized_email)

        logger.info(f"[MATCH] Retrieved {len(candidates_txn)} candidate transactions")

        if not candidates_txn:
            logger.warning(
                "[MATCH] No candidate transactions found - marking as 'no_candidates'"
            )
            result = MatchResult(
                email_id=email_db_id or 0,
                email_message_id=normalized_email.message_id,
                match_status="no_candidates",
                total_candidates_retrieved=0,
                total_candidates_scored=0,
            )
            result.add_note("No candidate transactions found within search criteria")

            if persist and email_db_id:
                logger.info(
                    f"[MATCH] Persisting 'no_candidates' result for email {email_db_id}"
                )
                await self._persist_match_result(result)

            return result

        # Step 2: Score candidates
        logger.info(f"[MATCH] Step 2: Scoring {len(candidates_txn)} candidates...")
        scored_candidates = self.scorer.score_all_candidates(
            normalized_email, candidates_txn
        )

        # Step 3: Rank and apply tie-breaking
        logger.info("[MATCH] Step 3: Ranking candidates and applying tie-breaking...")
        ranked_candidates = self.scorer.rank_candidates(scored_candidates)
        ranked_candidates = self.scorer.apply_tie_breaking(
            ranked_candidates, normalized_email
        )

        # Step 4: Create match result
        logger.info("[MATCH] Step 4: Creating match result with decision thresholds...")
        result = self.scorer.create_match_result(
            normalized_email, email_db_id or 0, ranked_candidates
        )

        # Step 5: Persist results
        if persist and email_db_id:
            logger.info(
                f"[MATCH] Step 5: Persisting match result (status: {result.match_status}, "
                f"confidence: {result.confidence:.2f})"
            )
            await self._persist_match_result(result)

            # Step 6: Execute post-processing actions
            if self.enable_actions:
                logger.info("[MATCH] Step 6: Executing post-processing actions...")
                await self._execute_actions(result, normalized_email)

        logger.info(
            f"[MATCH] ✓ Match completed for email: {normalized_email.message_id} | "
            f"Status: {result.match_status} | "
            f"Matched: {result.matched} | "
            f"Confidence: {result.confidence:.2f} | "
            f"Candidates scored: {len(scored_candidates)}"
        )

        return result

    async def match_batch(
        self,
        emails: Sequence[NormalizedEmail | ParsedEmail],
        email_db_ids: Sequence[int] | None = None,
        persist: bool = True,
    ) -> BatchMatchResult:
        """
        Match a batch of emails.

        Args:
            emails: List of emails to match
            email_db_ids: List of database IDs (must match length of emails if provided)
            persist: Whether to persist results

        Returns:
            Batch match result
        """
        if email_db_ids and len(email_db_ids) != len(emails):
            raise ValueError("email_db_ids must match length of emails")

        batch_result = BatchMatchResult()

        logger.info(f"[BATCH] Starting batch match for {len(emails)} emails")

        for i, email in enumerate(emails, 1):
            email_db_id = email_db_ids[i - 1] if email_db_ids else None

            try:
                logger.info(
                    f"[BATCH] Processing email {i}/{len(emails)} (ID: {email_db_id})"
                )
                result = await self.match_email(email, email_db_id, persist)
                batch_result.add_result(result)
                logger.debug(
                    f"[BATCH] Email {i}/{len(emails)} completed: {result.match_status}"
                )
            except Exception as e:
                logger.error(
                    f"[BATCH] Failed to match email {i}/{len(emails)} (ID: {email_db_id}): {e}",
                    exc_info=True,
                )

                # Update email with processing error if we have the ID
                if email_db_id and persist:
                    try:
                        email_record = await self.email_repo.get_by_id(email_db_id)
                        if email_record:
                            email_record.processing_error = str(e)
                            email_record.is_processed = (
                                False  # Mark as not processed due to error
                            )
                            await self.session.commit()
                            logger.debug(
                                f"[BATCH] Recorded processing error for email {email_db_id}"
                            )
                    except Exception as update_error:
                        logger.error(
                            f"[BATCH] Failed to update email error: {update_error}"
                        )
                        await self.session.rollback()

                # Create failed result
                failed_result = MatchResult(
                    email_id=email_db_id or 0,
                    email_message_id=getattr(email, "message_id", f"unknown_{i}"),
                    match_status="no_candidates",
                )
                failed_result.add_note(f"Error during matching: {str(e)}")
                batch_result.add_result(failed_result)

        batch_result.finalize()

        summary = batch_result.get_summary()
        logger.info(
            f"[BATCH] ✓ Batch match completed | "
            f"Total: {summary['total_emails']} | "
            f"Matched: {summary['matched']} | "
            f"Review: {summary['needs_review']} | "
            f"Rejected: {summary['rejected']} | "
            f"No candidates: {summary['no_candidates']} | "
            f"Avg confidence: {summary['average_confidence']:.2f}"
        )

        return batch_result

    async def match_unmatched_emails(
        self, limit: int | None = None
    ) -> BatchMatchResult:
        """
        Match all emails that haven't been matched yet.

        Args:
            limit: Maximum number of emails to process

        Returns:
            Batch match result
        """
        logger.info(f"[UNMATCHED] Starting match for unmatched emails (limit: {limit})")

        # Get unmatched emails using repository
        emails = await self.email_repo.get_unmatched(limit=limit)

        logger.info(f"[UNMATCHED] Found {len(emails)} unmatched emails to process")

        if not emails:
            return BatchMatchResult()

        # Convert to normalized emails
        normalized_emails = []
        email_db_ids = []

        for email in emails:
            try:
                # Create ParsedEmail from database model
                from app.emails.models import ParsedEmail as PE
                from decimal import Decimal

                # Validate parsing_method
                parsing_method = email.parsing_method or "regex"
                if parsing_method not in ("regex", "llm", "hybrid"):
                    parsing_method = "regex"

                parsed = PE(
                    message_id=email.message_id,
                    sender=email.sender,
                    subject=email.subject,
                    body=email.body,
                    received_at=email.received_at,
                    amount=Decimal(str(email.amount)) if email.amount else None,
                    currency=email.currency,
                    reference=email.reference,
                    account_number=email.account_info,  # Map account_info to account_number
                    email_timestamp=email.email_timestamp,  # Use email_timestamp
                    parsing_method=parsing_method,  # type: ignore
                    confidence=float(email.confidence) if email.confidence else 0.5,
                    is_alert=True,  # Emails in DB are assumed to be alerts
                )

                normalized = normalize_email(parsed)
                normalized_emails.append(normalized)
                email_db_ids.append(email.id)
            except Exception as e:
                logger.error(f"Failed to normalize email {email.id}: {e}")
                continue

        # Match batch
        return await self.match_batch(normalized_emails, email_db_ids, persist=True)

    async def rematch_email(self, email_db_id: int) -> MatchResult:
        """
        Re-match an email (update existing match).

        Args:
            email_db_id: Database ID of email

        Returns:
            Match result
        """
        logger.info(f"[REMATCH] Re-matching email ID: {email_db_id}")

        # Get email from database
        email = await self.email_repo.get_by_id(email_db_id)
        if not email:
            logger.error(f"[REMATCH] Email {email_db_id} not found in database")
            raise ValueError(f"Email {email_db_id} not found")

        # Delete existing match
        existing_match = await self.match_repo.get_by_email_id(email_db_id)
        if existing_match:
            await self.match_repo.delete(existing_match.id)
            await self.session.commit()
            logger.info(f"[REMATCH] Deleted existing match for email {email_db_id}")
        else:
            logger.debug(f"[REMATCH] No existing match found for email {email_db_id}")

        # Create parsed email
        from app.emails.models import ParsedEmail as PE
        from decimal import Decimal

        # Validate parsing_method
        parsing_method = email.parsing_method or "regex"
        if parsing_method not in ("regex", "llm", "hybrid"):
            parsing_method = "regex"

        parsed = PE(
            message_id=email.message_id,
            sender=email.sender,
            subject=email.subject,
            body=email.body,
            received_at=email.received_at,
            amount=Decimal(str(email.amount)) if email.amount else None,
            currency=email.currency,
            reference=email.reference,
            account_number=email.account_info,  # Map account_info to account_number
            email_timestamp=email.email_timestamp,  # Use email_timestamp
            parsing_method=parsing_method,  # type: ignore
            confidence=float(email.confidence) if email.confidence else 0.5,
            is_alert=True,  # Emails in DB are assumed to be alerts
        )

        # Match
        return await self.match_email(parsed, email_db_id, persist=True)

    async def _persist_match_result(self, result: MatchResult) -> None:
        """
        Persist match result to database.

        Args:
            result: Match result to persist
        """
        try:
            logger.debug(
                f"[PERSIST] Persisting match result for email {result.email_id}"
            )

            # Determine status based on match decision
            # Note: scorer returns "auto_matched", "needs_review", "rejected", "no_candidates"
            if result.match_status == "auto_matched":
                status = "matched"
            elif result.match_status == "needs_review":
                status = "review"
            elif result.match_status == "rejected":
                status = "rejected"
            elif result.match_status == "no_candidates":
                status = "no_candidates"
            else:
                status = "pending"  # Fallback for unknown states

            # Prepare match data
            match_data = {
                "email_id": result.email_id,
                "matched": result.matched,
                "confidence": float(result.confidence),
                "match_method": result.matching_method,
                "status": status,
            }

            # Add transaction ID if matched
            if result.best_candidate:
                # Look up transaction DB ID from external transaction ID using repository
                txn = await self.transaction_repo.get_by_transaction_id(
                    result.best_candidate.external_transaction_id
                )

                if txn:
                    match_data["transaction_id"] = txn.id
                    logger.debug(
                        f"[PERSIST] Linked to transaction DB ID {txn.id} "
                        f"(external: {result.best_candidate.external_transaction_id})"
                    )
                else:
                    logger.warning(
                        f"[PERSIST] Transaction {result.best_candidate.external_transaction_id} "
                        f"not found in database"
                    )

            # Serialize match details
            if result.best_candidate:
                match_data["match_details"] = json.dumps(
                    result.best_candidate.get_score_breakdown()
                )

            # Serialize alternative matches
            if result.alternative_candidates:
                alternatives = [
                    {
                        "transaction_id": c.external_transaction_id,
                        "score": c.total_score,
                        "rank": c.rank,
                    }
                    for c in result.alternative_candidates
                ]
                match_data["alternative_matches"] = json.dumps(alternatives)

            # Create or update match
            existing = await self.match_repo.get_by_email_id(result.email_id)

            if existing:
                # Update
                for key, value in match_data.items():
                    setattr(existing, key, value)
                await self.session.commit()
                logger.info(
                    f"[PERSIST] ✓ Updated match record for email {result.email_id}"
                )
            else:
                # Create new
                match = Match(**match_data)
                self.session.add(match)
                await self.session.commit()
                logger.info(
                    f"[PERSIST] ✓ Created new match record for email {result.email_id}"
                )

            # Mark email as processed
            email = await self.email_repo.get_by_id(result.email_id)
            if email:
                email.is_processed = True
                await self.session.commit()
                logger.debug(f"[PERSIST] ✓ Marked email {result.email_id} as processed")

        except Exception as e:
            logger.error(
                f"[PERSIST] Failed to persist match result for email {result.email_id}: {e}",
                exc_info=True,
            )
            await self.session.rollback()

            # Try to mark email with processing error
            try:
                email = await self.email_repo.get_by_id(result.email_id)
                if email:
                    email.processing_error = f"Persistence failed: {str(e)}"
                    email.is_processed = False
                    await self.session.commit()
            except Exception as error_update_failed:
                logger.error(
                    f"[PERSIST] Failed to update email error status: {error_update_failed}"
                )
                await self.session.rollback()

            raise

    @property
    def action_executor(self):
        """Lazy load action executor."""
        if self._action_executor is None:
            from app.actions.executor import ActionExecutor

            self._action_executor = ActionExecutor(self.session)
        return self._action_executor

    async def _execute_actions(
        self,
        result: MatchResult,
        normalized_email: NormalizedEmail,
    ) -> None:
        """
        Execute post-processing actions for a match result.

        Args:
            result: Match result
            normalized_email: Normalized email data
        """
        try:
            # Get match record to retrieve match_id
            match = await self.match_repo.get_by_email_id(result.email_id)
            if not match:
                logger.warning(
                    f"[ACTIONS] Match record not found for email {result.email_id}, "
                    "skipping actions"
                )
                return

            # Get transaction ID if matched
            transaction_id = None
            if result.best_candidate:
                txn = await self.transaction_repo.get_by_transaction_id(
                    result.best_candidate.external_transaction_id
                )
                transaction_id = txn.id if txn else None

            # Build metadata for actions
            metadata = {
                "amount": float(normalized_email.amount or 0),
                "currency": normalized_email.currency,
                "reference": (
                    normalized_email.reference.original
                    if normalized_email.reference
                    else "N/A"
                ),
                "sender": (
                    normalized_email.enrichment.bank_name
                    if normalized_email.enrichment
                    else normalized_email.sender
                ),
                "alternative_candidates_count": len(result.alternative_candidates),
                "message_id": normalized_email.message_id,
            }

            # Execute actions asynchronously
            await self.action_executor.execute_with_retry(
                match_id=match.id,
                email_id=result.email_id,
                transaction_id=transaction_id,
                match_status=result.match_status,
                confidence=result.confidence,
                metadata=metadata,
                actor="matching_engine",
            )

            logger.info(f"[ACTIONS] ✓ Actions completed for match {match.id}")

        except Exception as e:
            logger.error(
                f"[ACTIONS] Failed to execute actions for email {result.email_id}: {e}",
                exc_info=True,
            )
            # Don't fail the match if actions fail


# Convenience functions
async def match_email(
    session: AsyncSession,
    email: NormalizedEmail | ParsedEmail,
    email_db_id: int | None = None,
    config: MatchingConfig | None = None,
    persist: bool = True,
) -> MatchResult:
    """
    Convenience function to match a single email.

    Args:
        session: Database session
        email: Email to match
        email_db_id: Database ID of email
        config: Matching configuration
        persist: Whether to persist results

    Returns:
        Match result
    """
    engine = MatchingEngine(session, config)
    return await engine.match_email(email, email_db_id, persist)


async def match_unmatched(
    session: AsyncSession,
    limit: int | None = None,
    config: MatchingConfig | None = None,
) -> BatchMatchResult:
    """
    Convenience function to match all unmatched emails.

    Args:
        session: Database session
        limit: Maximum number to process
        config: Matching configuration

    Returns:
        Batch match result
    """
    engine = MatchingEngine(session, config)
    return await engine.match_unmatched_emails(limit)
