"""Log repository with specialized queries."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import select, desc

from app.db.models.log import Log
from app.db.repository import BaseRepository


class LogRepository(BaseRepository[Log]):
    """Repository for Log model with specialized queries."""

    async def create_log(
        self,
        level: str,
        event: str,
        message: str,
        component: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[str] = None,
        exception: Optional[str] = None,
        email_id: Optional[int] = None,
        transaction_id: Optional[int] = None,
        match_id: Optional[int] = None,
    ) -> Log:
        """
        Create a new log entry.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            event: Event type
            message: Log message
            component: Component name
            request_id: Request ID for tracing
            details: JSON details
            exception: Exception traceback
            email_id: Related email ID
            transaction_id: Related transaction ID
            match_id: Related match ID
            
        Returns:
            Created log instance
        """
        return await self.create(
            level=level,
            event=event,
            message=message,
            component=component,
            request_id=request_id,
            details=details,
            exception=exception,
            email_id=email_id,
            transaction_id=transaction_id,
            match_id=match_id,
        )

    async def get_by_level(
        self, level: str, limit: Optional[int] = None
    ) -> List[Log]:
        """
        Get logs by level.
        
        Args:
            level: Log level
            limit: Maximum number to return
            
        Returns:
            List of logs
        """
        query = (
            select(self.model)
            .where(self.model.level == level)
            .order_by(desc(self.model.timestamp))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_event(
        self, event: str, limit: Optional[int] = None
    ) -> List[Log]:
        """
        Get logs by event type.
        
        Args:
            event: Event type
            limit: Maximum number to return
            
        Returns:
            List of logs
        """
        query = (
            select(self.model)
            .where(self.model.event == event)
            .order_by(desc(self.model.timestamp))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_component(
        self, component: str, limit: Optional[int] = None
    ) -> List[Log]:
        """
        Get logs by component.
        
        Args:
            component: Component name
            limit: Maximum number to return
            
        Returns:
            List of logs
        """
        query = (
            select(self.model)
            .where(self.model.component == component)
            .order_by(desc(self.model.timestamp))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_request_id(self, request_id: str) -> List[Log]:
        """
        Get all logs for a specific request (for tracing).
        
        Args:
            request_id: Request ID
            
        Returns:
            List of logs for that request
        """
        query = (
            select(self.model)
            .where(self.model.request_id == request_id)
            .order_by(self.model.timestamp.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_errors(
        self, hours: Optional[int] = 24, limit: Optional[int] = None
    ) -> List[Log]:
        """
        Get error and critical logs from the last N hours.
        
        Args:
            hours: Hours back to look
            limit: Maximum number to return
            
        Returns:
            List of error logs
        """
        hours_value = hours if hours is not None else 24
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_value)
        query = (
            select(self.model)
            .where(
                self.model.level.in_(["ERROR", "CRITICAL"]),
                self.model.timestamp >= cutoff,
            )
            .order_by(desc(self.model.timestamp))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent(
        self, hours: int = 24, limit: Optional[int] = 100
    ) -> List[Log]:
        """
        Get recent logs.
        
        Args:
            hours: Hours back to look
            limit: Maximum number to return
            
        Returns:
            List of recent logs
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = (
            select(self.model)
            .where(self.model.timestamp >= cutoff)
            .order_by(desc(self.model.timestamp))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def cleanup_old_logs(self, days: int) -> int:
        """
        Delete logs older than specified days.
        
        Args:
            days: Age threshold
            
        Returns:
            Number of deleted records
        """
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.session.execute(
            delete(self.model).where(self.model.timestamp < cutoff)
        )
        return result.rowcount or 0  # type: ignore
