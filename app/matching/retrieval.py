"""Candidate retrieval for matching engine."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.transaction import Transaction
from app.db.repositories.transaction_repository import TransactionRepository
from app.matching.config import MatchingConfig
from app.normalization.models import NormalizedEmail, NormalizedTransaction

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CandidateRetriever:
    """Retrieves candidate transactions for matching."""

    def __init__(self, session: AsyncSession, config: MatchingConfig | None = None):
        """
        Initialize candidate retriever.

        Args:
            session: Database session
            config: Matching configuration
        """
        self.session = session
        self.config = config or MatchingConfig()
        self.retrieval_config = self.config.candidate_retrieval

        # Initialize repository
        self.transaction_repo = TransactionRepository(Transaction, session)

    async def get_candidates_for_email(
        self,
        email: NormalizedEmail,
        time_window_hours: int | None = None,
    ) -> list[NormalizedTransaction]:
        """
        Retrieve candidate transactions for an email.

        Args:
            email: Normalized email to match
            time_window_hours: Custom time window (default: from config)

        Returns:
            List of candidate transactions
        """
        if email.amount is None:
            logger.warning(
                f"[RETRIEVAL] Email {email.message_id} has no amount - cannot retrieve candidates"
            )
            return []

        # Use configured time window if not specified
        if time_window_hours is None:
            time_window_hours = self.config.time_window.default_hours

        logger.info(
            f"[RETRIEVAL] Searching for candidates | "
            f"Email: {email.message_id} | "
            f"Amount: {email.amount} {email.currency} | "
            f"Time window: {time_window_hours}h | "
            f"Tolerance: {self.retrieval_config.amount_tolerance_percent}%"
        )

        # Use repository to get candidates
        transactions = await self.transaction_repo.get_candidates_for_matching(
            amount=email.amount,
            currency=email.currency,
            timestamp=email.timestamp,
            time_window_hours=time_window_hours,
            amount_tolerance_percent=self.retrieval_config.amount_tolerance_percent,
            require_same_currency=self.retrieval_config.require_same_currency,
            exclude_already_matched=self.retrieval_config.exclude_already_matched,
        )

        logger.info(
            f"[RETRIEVAL] Database query returned {len(transactions)} candidate transactions"
        )

        # Convert to NormalizedTransaction
        candidates = []
        for txn in transactions:
            try:
                normalized = self._convert_to_normalized(txn)
                candidates.append(normalized)
            except Exception as e:
                logger.error(f"[RETRIEVAL] Failed to convert transaction {txn.id}: {e}")
                continue

        logger.debug(
            f"[RETRIEVAL] Converted {len(candidates)} transactions to normalized format"
        )

        # Apply additional filtering (post-process for extra safety)
        candidates_before_filter = len(candidates)
        candidates = self._post_filter_candidates(email, candidates)

        if candidates_before_filter != len(candidates):
            logger.info(
                f"[RETRIEVAL] Post-filtering removed {candidates_before_filter - len(candidates)} candidates"
            )

        # Limit candidates
        if len(candidates) > self.retrieval_config.max_candidates:
            logger.warning(
                f"[RETRIEVAL] Limiting candidates from {len(candidates)} to {self.retrieval_config.max_candidates}"
            )
            candidates = candidates[: self.retrieval_config.max_candidates]

        logger.info(f"[RETRIEVAL] ✓ Returning {len(candidates)} final candidates")
        return candidates

    def _convert_to_normalized(self, transaction: Transaction) -> NormalizedTransaction:
        """
        Convert Transaction ORM model to NormalizedTransaction.

        Args:
            transaction: Transaction ORM model

        Returns:
            NormalizedTransaction
        """
        # Import here to avoid circular imports
        from app.normalization.normalizer import normalize_transaction

        # Convert to normalized format
        return normalize_transaction(
            transaction_id=transaction.transaction_id,
            external_source=transaction.external_source,
            amount=Decimal(str(transaction.amount)),
            currency=transaction.currency,
            timestamp=transaction.transaction_timestamp,
            reference=transaction.reference,
            account_ref=transaction.account_ref,
            description=transaction.description,
        )

    def _post_filter_candidates(
        self, email: NormalizedEmail, candidates: list[NormalizedTransaction]
    ) -> list[NormalizedTransaction]:
        """
        Apply additional filtering after retrieval.

        Args:
            email: Normalized email
            candidates: Retrieved candidates

        Returns:
            Filtered candidates
        """
        filtered = []
        filtered_out_count = 0

        for candidate in candidates:
            # Skip if amount mismatch (shouldn't happen, but double-check)
            if email.amount and candidate.amount:
                tolerance = self.retrieval_config.amount_tolerance_percent
                diff = abs(email.amount - candidate.amount)
                max_diff = email.amount * Decimal(str(tolerance))

                if diff > max_diff:
                    logger.debug(
                        f"[RETRIEVAL] Filtering transaction {candidate.transaction_id}: "
                        f"amount mismatch (email: {email.amount}, txn: {candidate.amount})"
                    )
                    filtered_out_count += 1
                    continue

            # Skip if currency mismatch (if required)
            if self.retrieval_config.require_same_currency:
                if (
                    email.currency
                    and candidate.currency
                    and email.currency != candidate.currency
                ):
                    logger.debug(
                        f"[RETRIEVAL] Filtering transaction {candidate.transaction_id}: "
                        f"currency mismatch (email: {email.currency}, txn: {candidate.currency})"
                    )
                    filtered_out_count += 1
                    continue

            filtered.append(candidate)

        if filtered_out_count > 0:
            logger.debug(
                f"[RETRIEVAL] Post-filter removed {filtered_out_count} candidates"
            )

        return filtered

    async def get_candidates_by_composite_key(
        self,
        email: NormalizedEmail,
    ) -> list[NormalizedTransaction]:
        """
        Retrieve candidates using composite key matching.

        This is a faster lookup method if composite keys are indexed.

        Args:
            email: Normalized email

        Returns:
            List of candidate transactions
        """
        if not email.composite_key:
            logger.warning(f"Email {email.message_id} has no composite key")
            return []

        # Extract parameters from composite key
        amount = None
        currency = None
        timestamp = None

        if email.composite_key.amount_str:
            amount = Decimal(email.composite_key.amount_str)

        if email.composite_key.currency:
            currency = email.composite_key.currency

        # Parse date bucket (YYYY-MM-DD-HH format)
        if email.composite_key.date_bucket:
            try:
                from datetime import datetime

                date_parts = email.composite_key.date_bucket.split("-")
                if len(date_parts) == 4:
                    year, month, day, hour = map(int, date_parts)
                    timestamp = datetime(year, month, day, hour)
            except Exception as e:
                logger.error(f"Failed to parse date bucket: {e}")

        # If we don't have enough information, return empty
        if not amount:
            logger.warning(f"Composite key has no amount for email {email.message_id}")
            return []

        # Use repository with 1-hour window for composite key (tighter than normal)
        transactions = await self.transaction_repo.get_candidates_for_matching(
            amount=amount,
            currency=currency,
            timestamp=timestamp,
            time_window_hours=1,  # Tighter window for composite key matching
            amount_tolerance_percent=self.retrieval_config.amount_tolerance_percent,
            require_same_currency=self.retrieval_config.require_same_currency,
            exclude_already_matched=self.retrieval_config.exclude_already_matched,
        )

        # Convert to normalized
        candidates = []
        for txn in transactions:
            try:
                normalized = self._convert_to_normalized(txn)
                candidates.append(normalized)
            except Exception as e:
                logger.error(f"Failed to convert transaction {txn.id}: {e}")
                continue

        logger.info(
            f"Retrieved {len(candidates)} candidates using composite key for email {email.message_id}"
        )

        return candidates


async def get_candidates(
    session: AsyncSession,
    email: NormalizedEmail,
    config: MatchingConfig | None = None,
    time_window_hours: int | None = None,
) -> list[NormalizedTransaction]:
    """
    Convenience function to retrieve candidates.

    Args:
        session: Database session
        email: Normalized email
        config: Matching configuration
        time_window_hours: Custom time window

    Returns:
        List of candidate transactions
    """
    retriever = CandidateRetriever(session, config)
    return await retriever.get_candidates_for_email(email, time_window_hours)
