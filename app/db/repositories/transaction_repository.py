"""Transaction repository with specialized queries."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import select, and_, or_

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
            .where(self.model.is_verified == False)
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
        query = select(self.model).where(
            self.model.transaction_timestamp >= cutoff
        ).order_by(self.model.transaction_timestamp.desc())
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
        query = select(self.model).where(
            self.model.reference.ilike(f"%{reference}%")
        )
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
