"""Main matching engine that orchestrates the reconciliation process."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

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
        config: MatchingConfig | None = None
    ):
        """
        Initialize matching engine.
        
        Args:
            session: Database session
            config: Matching configuration
        """
        self.session = session
        self.config = config or MatchingConfig()
        self.config.validate_config()
        
        # Initialize components
        self.retriever = CandidateRetriever(session, config)
        self.scorer = MatchScorer(config)
        
        # Initialize repositories
        from app.db.models.email import Email
        from app.db.models.match import Match
        self.email_repo = EmailRepository(Email, self.session)
        self.match_repo = MatchRepository(Match, self.session)
        
        logger.info("MatchingEngine initialized", extra={"config": self.config.model_dump()})
        
    async def match_email(
        self,
        email: NormalizedEmail | ParsedEmail,
        email_db_id: int | None = None,
        persist: bool = True
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
            logger.info(f"Normalizing email {email.message_id}")
            from app.emails.models import ParsedEmail as PE
            if isinstance(email, PE):
                normalized_email = normalize_email(email)
            else:
                raise ValueError(f"Unsupported email type: {type(email)}")
        else:
            normalized_email = email
            
        logger.info(
            f"Starting match for email {normalized_email.message_id}",
            extra={
                "email_id": email_db_id,
                "amount": str(normalized_email.amount) if normalized_email.amount else None,
                "currency": normalized_email.currency,
            }
        )
        
        # Step 1: Retrieve candidates
        candidates_txn = await self.retriever.get_candidates_for_email(normalized_email)
        
        logger.info(
            f"Retrieved {len(candidates_txn)} candidates for email {normalized_email.message_id}"
        )
        
        if not candidates_txn:
            result = MatchResult(
                email_id=email_db_id or 0,
                email_message_id=normalized_email.message_id,
                match_status="no_candidates",
                total_candidates_retrieved=0,
                total_candidates_scored=0,
            )
            result.add_note("No candidate transactions found within search criteria")
            
            if persist and email_db_id:
                await self._persist_match_result(result)
                
            return result
            
        # Step 2: Score candidates
        scored_candidates = self.scorer.score_all_candidates(normalized_email, candidates_txn)
        
        # Step 3: Rank and apply tie-breaking
        ranked_candidates = self.scorer.rank_candidates(scored_candidates)
        ranked_candidates = self.scorer.apply_tie_breaking(ranked_candidates, normalized_email)
        
        # Step 4: Create match result
        result = self.scorer.create_match_result(
            normalized_email,
            email_db_id or 0,
            ranked_candidates
        )
        
        # Step 5: Persist results
        if persist and email_db_id:
            await self._persist_match_result(result)
            
        logger.info(
            f"Completed match for email {normalized_email.message_id}",
            extra={
                "status": result.match_status,
                "matched": result.matched,
                "confidence": result.confidence,
                "candidates": len(scored_candidates),
            }
        )
        
        return result
        
    async def match_batch(
        self,
        emails: list[NormalizedEmail | ParsedEmail],
        email_db_ids: list[int] | None = None,
        persist: bool = True
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
        
        logger.info(f"Starting batch match for {len(emails)} emails")
        
        for i, email in enumerate(emails):
            email_db_id = email_db_ids[i] if email_db_ids else None
            
            try:
                result = await self.match_email(email, email_db_id, persist)
                batch_result.add_result(result)
            except Exception as e:
                logger.error(
                    f"Failed to match email at index {i}: {e}",
                    exc_info=True
                )
                # Create failed result
                failed_result = MatchResult(
                    email_id=email_db_id or 0,
                    email_message_id=getattr(email, 'message_id', f'unknown_{i}'),
                    match_status="no_candidates",
                )
                failed_result.add_note(f"Error during matching: {str(e)}")
                batch_result.add_result(failed_result)
                
        batch_result.finalize()
        
        logger.info(
            f"Completed batch match",
            extra=batch_result.get_summary()
        )
        
        return batch_result
        
    async def match_unmatched_emails(
        self,
        limit: int | None = None
    ) -> BatchMatchResult:
        """
        Match all emails that haven't been matched yet.
        
        Args:
            limit: Maximum number of emails to process
            
        Returns:
            Batch match result
        """
        logger.info("Starting match for unmatched emails", extra={"limit": limit})
        
        # Get unmatched emails from database
        # First, get all email IDs that don't have a match record
        from sqlalchemy import select, outerjoin
        
        query = (
            select(Email)
            .outerjoin(Match, Email.id == Match.email_id)
            .where(Match.id.is_(None))
            .order_by(Email.created_at.desc())
        )
        
        if limit:
            query = query.limit(limit)
            
        result = await self.session.execute(query)
        emails = result.scalars().all()
        
        logger.info(f"Found {len(emails)} unmatched emails")
        
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
        
    async def rematch_email(
        self,
        email_db_id: int
    ) -> MatchResult:
        """
        Re-match an email (update existing match).
        
        Args:
            email_db_id: Database ID of email
            
        Returns:
            Match result
        """
        logger.info(f"Re-matching email {email_db_id}")
        
        # Get email from database
        email = await self.email_repo.get_by_id(email_db_id)
        if not email:
            raise ValueError(f"Email {email_db_id} not found")
            
        # Delete existing match
        existing_match = await self.match_repo.get_by_email_id(email_db_id)
        if existing_match:
            await self.match_repo.delete(existing_match.id)
            await self.session.commit()
            logger.info(f"Deleted existing match for email {email_db_id}")
            
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
            # Prepare match data
            match_data = {
                "email_id": result.email_id,
                "matched": result.matched,
                "confidence": float(result.confidence),
                "match_method": result.matching_method,
                "status": "pending",  # Default status
            }
            
            # Add transaction ID if matched
            if result.best_candidate:
                # Need to look up transaction DB ID from external transaction ID
                from app.db.models.transaction import Transaction
                from sqlalchemy import select
                
                query = select(Transaction.id).where(
                    Transaction.transaction_id == result.best_candidate.external_transaction_id
                )
                txn_result = await self.session.execute(query)
                txn_id = txn_result.scalar_one_or_none()
                
                if txn_id:
                    match_data["transaction_id"] = txn_id
                else:
                    logger.warning(
                        f"Transaction {result.best_candidate.external_transaction_id} not found in database"
                    )
                    
            # Serialize match details
            if result.best_candidate:
                match_data["match_details"] = json.dumps(result.best_candidate.get_score_breakdown())
                
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
                logger.info(f"Updated match for email {result.email_id}")
            else:
                # Create new
                match = Match(**match_data)
                self.session.add(match)
                await self.session.commit()
                logger.info(f"Created new match for email {result.email_id}")
                
        except Exception as e:
            logger.error(f"Failed to persist match result: {e}", exc_info=True)
            await self.session.rollback()
            raise


# Convenience functions
async def match_email(
    session: AsyncSession,
    email: NormalizedEmail | ParsedEmail,
    email_db_id: int | None = None,
    config: MatchingConfig | None = None,
    persist: bool = True
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
    config: MatchingConfig | None = None
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
