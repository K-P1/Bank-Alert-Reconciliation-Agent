"""Candidate retrieval for matching engine."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.transaction import Transaction
from app.db.models.match import Match
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
                f"Email {email.message_id} has no amount, cannot retrieve candidates"
            )
            return []

        # Use configured time window if not specified
        if time_window_hours is None:
            time_window_hours = self.config.time_window.default_hours

        # Build query
        query = self._build_candidate_query(email, time_window_hours)

        # Execute query
        result = await self.session.execute(query)
        transactions = result.scalars().all()

        logger.info(
            f"Retrieved {len(transactions)} candidates for email {email.message_id}",
            extra={
                "email_amount": str(email.amount),
                "currency": email.currency,
                "time_window_hours": time_window_hours,
            },
        )

        # Convert to NormalizedTransaction
        candidates = []
        for txn in transactions:
            try:
                normalized = self._convert_to_normalized(txn)
                candidates.append(normalized)
            except Exception as e:
                logger.error(f"Failed to convert transaction {txn.id}: {e}")
                continue

        # Apply additional filtering
        candidates = self._post_filter_candidates(email, candidates)

        # Limit candidates
        if len(candidates) > self.retrieval_config.max_candidates:
            logger.warning(
                f"Limiting candidates from {len(candidates)} to {self.retrieval_config.max_candidates}"
            )
            candidates = candidates[: self.retrieval_config.max_candidates]

        return candidates

    def _build_candidate_query(self, email: NormalizedEmail, time_window_hours: int):
        """
        Build SQL query for candidate retrieval.

        Args:
            email: Normalized email
            time_window_hours: Time window in hours

        Returns:
            SQLAlchemy query
        """
        query = select(Transaction)

        conditions = []

        # Amount filter (with tolerance)
        if email.amount is not None:
            tolerance = self.retrieval_config.amount_tolerance_percent
            min_amount = email.amount * Decimal(str(1 - tolerance))
            max_amount = email.amount * Decimal(str(1 + tolerance))

            conditions.append(Transaction.amount >= float(min_amount))
            conditions.append(Transaction.amount <= float(max_amount))

        # Currency filter
        if self.retrieval_config.require_same_currency and email.currency:
            conditions.append(Transaction.currency == email.currency)

        # Time window filter
        if email.timestamp:
            start_time = email.timestamp - timedelta(hours=time_window_hours)
            end_time = email.timestamp + timedelta(hours=time_window_hours)

            conditions.append(Transaction.transaction_timestamp >= start_time)
            conditions.append(Transaction.transaction_timestamp <= end_time)

        # Exclude already matched transactions (optional)
        if self.retrieval_config.exclude_already_matched:
            # Subquery to find already matched transaction IDs
            matched_subquery = (
                select(Match.transaction_id)
                .where(Match.matched.is_(True))
                .where(Match.transaction_id.isnot(None))
            )
            conditions.append(Transaction.id.notin_(matched_subquery))

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Order by timestamp (closest first) and amount match
        if email.timestamp:
            # Note: SQLite doesn't support ABS on datetime, so we'll sort in Python
            query = query.order_by(Transaction.transaction_timestamp)
        else:
            query = query.order_by(Transaction.created_at.desc())

        return query

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

        for candidate in candidates:
            # Skip if amount mismatch (shouldn't happen, but double-check)
            if email.amount and candidate.amount:
                tolerance = self.retrieval_config.amount_tolerance_percent
                diff = abs(email.amount - candidate.amount)
                max_diff = email.amount * Decimal(str(tolerance))

                if diff > max_diff:
                    logger.debug(
                        f"Filtering out transaction {candidate.transaction_id}: amount mismatch",
                        extra={
                            "email_amount": str(email.amount),
                            "txn_amount": str(candidate.amount),
                            "difference": str(diff),
                        },
                    )
                    continue

            # Skip if currency mismatch (if required)
            if self.retrieval_config.require_same_currency:
                if (
                    email.currency
                    and candidate.currency
                    and email.currency != candidate.currency
                ):
                    logger.debug(
                        f"Filtering out transaction {candidate.transaction_id}: currency mismatch",
                        extra={
                            "email_currency": email.currency,
                            "txn_currency": candidate.currency,
                        },
                    )
                    continue

            filtered.append(candidate)

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

        # Build query based on composite key components
        query = select(Transaction)

        conditions = []

        # Amount (from composite key)
        if email.composite_key.amount_str:
            amount = Decimal(email.composite_key.amount_str)
            tolerance = self.retrieval_config.amount_tolerance_percent
            min_amount = amount * Decimal(str(1 - tolerance))
            max_amount = amount * Decimal(str(1 + tolerance))

            conditions.append(Transaction.amount >= float(min_amount))
            conditions.append(Transaction.amount <= float(max_amount))

        # Currency
        if email.composite_key.currency:
            conditions.append(Transaction.currency == email.composite_key.currency)

        # Date bucket (extract date from timestamp)
        # Note: This requires parsing the date_bucket format (YYYY-MM-DD-HH)
        if email.composite_key.date_bucket:
            # Parse date bucket
            try:
                from datetime import datetime

                date_parts = email.composite_key.date_bucket.split("-")
                if len(date_parts) == 4:
                    year, month, day, hour = map(int, date_parts)
                    bucket_start = datetime(year, month, day, hour)
                    bucket_end = bucket_start + timedelta(hours=1)

                    conditions.append(Transaction.transaction_timestamp >= bucket_start)
                    conditions.append(Transaction.transaction_timestamp < bucket_end)
            except Exception as e:
                logger.error(f"Failed to parse date bucket: {e}")

        # Apply conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Execute
        result = await self.session.execute(query)
        transactions = result.scalars().all()

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
