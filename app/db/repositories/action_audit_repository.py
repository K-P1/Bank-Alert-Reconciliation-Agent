"""Repository for action audit logs."""

from typing import Optional, Sequence
from datetime import datetime, timedelta, timezone

from app.db.models.action_audit import ActionAudit
from app.db.repository import BaseRepository


class ActionAuditRepository(BaseRepository[ActionAudit]):
    """Repository for action audit log operations."""

    async def get_by_action_id(self, action_id: str) -> Optional[ActionAudit]:
        """Get action audit by action ID."""
        results = await self.filter(action_id=action_id)
        return results[0] if results else None

    async def get_by_match_id(
        self,
        match_id: int,
        action_type: Optional[str] = None,
    ) -> Sequence[ActionAudit]:
        """Get all actions for a match, optionally filtered by type."""
        filters: dict = {"match_id": match_id}
        if action_type:
            filters["action_type"] = action_type
        return await self.filter(**filters)

    async def get_by_email_id(
        self,
        email_id: int,
        action_type: Optional[str] = None,
    ) -> Sequence[ActionAudit]:
        """Get all actions for an email, optionally filtered by type."""
        filters: dict = {"email_id": email_id}
        if action_type:
            filters["action_type"] = action_type
        return await self.filter(**filters)

    async def get_failed_actions(
        self,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Sequence[ActionAudit]:
        """Get failed actions, optionally filtered by time."""
        filters: dict = {"status": "failed"}
        if since:
            filters["started_at__gte"] = since
        return await self.filter(**filters, limit=limit)

    async def get_pending_actions(
        self,
        older_than_minutes: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Sequence[ActionAudit]:
        """Get pending actions, optionally those stuck for too long."""
        filters: dict = {"status": "pending"}
        if older_than_minutes:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
            filters["started_at__lt"] = cutoff
        return await self.filter(**filters, limit=limit)

    async def get_by_outcome(
        self,
        outcome: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Sequence[ActionAudit]:
        """Get actions by match outcome."""
        filters: dict = {"match_outcome": outcome}
        if since:
            filters["started_at__gte"] = since
        return await self.filter(**filters, limit=limit)

    async def get_by_actor(
        self,
        actor: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Sequence[ActionAudit]:
        """Get actions by actor."""
        filters: dict = {"actor": actor}
        if since:
            filters["started_at__gte"] = since
        return await self.filter(**filters, limit=limit)

    async def get_statistics(
        self,
        since: Optional[datetime] = None,
    ) -> dict:
        """Get action execution statistics."""
        filters = {}
        if since:
            filters["started_at__gte"] = since

        all_actions = await self.filter(**filters)

        stats = {
            "total": len(all_actions),
            "success": sum(1 for a in all_actions if a.status == "success"),
            "failed": sum(1 for a in all_actions if a.status == "failed"),
            "pending": sum(1 for a in all_actions if a.status == "pending"),
            "retrying": sum(1 for a in all_actions if a.status == "retrying"),
            "by_type": {},
            "by_outcome": {},
            "avg_duration_ms": 0,
        }

        # Count by type
        for action in all_actions:
            stats["by_type"][action.action_type] = (
                stats["by_type"].get(action.action_type, 0) + 1
            )
            stats["by_outcome"][action.match_outcome] = (
                stats["by_outcome"].get(action.match_outcome, 0) + 1
            )

        # Average duration (only completed actions)
        completed = [a for a in all_actions if a.duration_ms is not None]
        if completed:
            total_duration = sum(a.duration_ms for a in completed if a.duration_ms)
            stats["avg_duration_ms"] = total_duration / len(completed)

        return stats

    async def delete_old_audits(self, retention_days: int) -> int:
        """Delete audit logs older than retention period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        old_audits = await self.filter(created_at__lt=cutoff)

        count = 0
        for audit in old_audits:
            await self.delete(audit.id)
            count += 1

        return count
