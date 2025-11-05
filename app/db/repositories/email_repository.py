"""Email repository with specialized queries."""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, and_

from app.db.models.email import Email
from app.db.repository import BaseRepository


class EmailRepository(BaseRepository[Email]):
    """Repository for Email model with specialized queries."""

    async def get_by_message_id(self, message_id: str) -> Optional[Email]:
        """Get an email by its message ID."""
        return await self.get_by_field("message_id", message_id)

    async def get_unprocessed(self, limit: Optional[int] = None) -> List[Email]:
        """
        Get unprocessed emails.

        Args:
            limit: Maximum number of emails to return

        Returns:
            List of unprocessed emails
        """
        query = (
            select(self.model)
            .where(self.model.is_processed.is_(False))
            .order_by(self.model.parsed_at.asc())
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_amount_and_timerange(
        self, amount: float, start_time: datetime, end_time: datetime
    ) -> List[Email]:
        """
        Get emails by amount within a time range.

        Args:
            amount: Transaction amount
            start_time: Start of time window
            end_time: End of time window

        Returns:
            List of matching emails
        """
        query = select(self.model).where(
            and_(
                self.model.amount == amount,
                self.model.email_timestamp >= start_time,
                self.model.email_timestamp <= end_time,
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_old_emails(self, days: int) -> List[Email]:
        """
        Get emails older than specified days (for archival/cleanup).

        Args:
            days: Age threshold in days

        Returns:
            List of old emails
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = select(self.model).where(self.model.parsed_at < cutoff_date)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_as_processed(self, email_id: int) -> Optional[Email]:
        """
        Mark an email as processed.

        Args:
            email_id: Email ID

        Returns:
            Updated email instance
        """
        return await self.update(email_id, is_processed=True)

    async def get_by_reference(self, reference: str) -> List[Email]:
        """
        Get emails by reference code.

        Args:
            reference: Transaction reference

        Returns:
            List of matching emails
        """
        query = select(self.model).where(self.model.reference.ilike(f"%{reference}%"))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_unprocessed(self) -> int:
        """Get count of unprocessed emails."""
        return await self.count(is_processed=False)
