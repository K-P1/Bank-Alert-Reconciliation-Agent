"""Transaction repository with specialized queries."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import select, and_

from app.db.models.transaction import Transaction
from app.db.repository import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for Transaction model with specialized queries."""

    async def get_by_transaction_id(self, transaction_id: str) -> Optional[Transaction]:
        """Get a transaction by its external transaction ID."""
        return await self.get_by_field("transaction_id", transaction_id)

    async def get_unverified(self, limit: Optional[int] = None) -> List[Transaction]:
        """
        Get unverified transactions.

        Args:
            limit: Maximum number of transactions to return

        Returns:
            List of unverified transactions
        """
        query = (
            select(self.model)
            .where(self.model.is_verified.is_(False))
            .order_by(self.model.transaction_timestamp.desc())
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_amount_and_timerange(
        self, amount: float, start_time: datetime, end_time: datetime
    ) -> List[Transaction]:
        """
        Get transactions by amount within a time range.

        Args:
            amount: Transaction amount
            start_time: Start of time window
            end_time: End of time window

        Returns:
            List of matching transactions
        """
        query = select(self.model).where(
            and_(
                self.model.amount == amount,
                self.model.transaction_timestamp >= start_time,
                self.model.transaction_timestamp <= end_time,
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent(self, hours: int = 48) -> List[Transaction]:
        """
        Get recent transactions within the specified hours.

        Args:
            hours: Number of hours back to look

        Returns:
            List of recent transactions
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = (
            select(self.model)
            .where(self.model.transaction_timestamp >= cutoff)
            .order_by(self.model.transaction_timestamp.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_as_verified(
        self, transaction_id: int, verified_at: Optional[datetime] = None
    ) -> Optional[Transaction]:
        """
        Mark a transaction as verified.

        Args:
            transaction_id: Transaction ID
            verified_at: Verification timestamp (defaults to now)

        Returns:
            Updated transaction instance
        """
        if verified_at is None:
            verified_at = datetime.now(timezone.utc)
        return await self.update(
            transaction_id, is_verified=True, verified_at=verified_at, status="verified"
        )

    async def get_by_reference(self, reference: str) -> List[Transaction]:
        """
        Get transactions by reference code.

        Args:
            reference: Transaction reference

        Returns:
            List of matching transactions
        """
        query = select(self.model).where(self.model.reference.ilike(f"%{reference}%"))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_source(
        self, source: str, limit: Optional[int] = None
    ) -> List[Transaction]:
        """
        Get transactions by external source.

        Args:
            source: External source name
            limit: Maximum number to return

        Returns:
            List of transactions from that source
        """
        query = select(self.model).where(self.model.external_source == source)
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_unverified(self) -> int:
        """Get count of unverified transactions."""
        return await self.count(is_verified=False)

    async def count_by_status(self, status: str) -> int:
        """Get count of transactions with specific status."""
        return await self.count(status=status)

    async def get_candidates_for_matching(
        self,
        amount: Decimal,
        currency: Optional[str],
        timestamp: Optional[datetime],
        time_window_hours: int,
        amount_tolerance_percent: float = 0.02,
        require_same_currency: bool = True,
        exclude_already_matched: bool = True,
    ) -> List[Transaction]:
        """
        Get candidate transactions for matching based on email criteria.

        Args:
            amount: Transaction amount
            currency: Currency code
            timestamp: Email timestamp
            time_window_hours: Time window in hours
            amount_tolerance_percent: Tolerance for amount matching (default 2%)
            require_same_currency: Whether to require same currency
            exclude_already_matched: Whether to exclude already matched transactions

        Returns:
            List of candidate transactions
        """
        from app.db.models.match import Match

        query = select(self.model)
        conditions = []

        # Amount filter (with tolerance)
        min_amount = amount * Decimal(str(1 - amount_tolerance_percent))
        max_amount = amount * Decimal(str(1 + amount_tolerance_percent))
        conditions.append(self.model.amount >= float(min_amount))
        conditions.append(self.model.amount <= float(max_amount))

        # Currency filter
        if require_same_currency and currency:
            conditions.append(self.model.currency == currency)

        # Time window filter
        if timestamp:
            start_time = timestamp - timedelta(hours=time_window_hours)
            end_time = timestamp + timedelta(hours=time_window_hours)
            conditions.append(self.model.transaction_timestamp >= start_time)
            conditions.append(self.model.transaction_timestamp <= end_time)

        # Exclude already matched transactions
        if exclude_already_matched:
            matched_subquery = (
                select(Match.transaction_id)
                .where(Match.matched.is_(True))
                .where(Match.transaction_id.isnot(None))
            )
            conditions.append(self.model.id.notin_(matched_subquery))

        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))

        # Order by timestamp
        if timestamp:
            query = query.order_by(self.model.transaction_timestamp)
        else:
            query = query.order_by(self.model.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())
