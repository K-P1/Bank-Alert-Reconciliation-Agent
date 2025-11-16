"""Match repository with specialized queries."""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, desc

from app.db.models.match import Match
from app.db.repository import BaseRepository


class MatchRepository(BaseRepository[Match]):
    """Repository for Match model with specialized queries."""

    async def get_by_email_id(self, email_id: int) -> Optional[Match]:
        """Get a match by email ID."""
        return await self.get_by_field("email_id", email_id)

    async def exists_for_email(self, email_id: int) -> bool:
        """
        Check if a match exists for an email.

        Args:
            email_id: Email ID

        Returns:
            True if a match exists, False otherwise
        """
        return await self.exists(email_id=email_id)

    async def get_by_transaction_id(self, transaction_id: int) -> List[Match]:
        """
        Get all matches for a transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            List of matches
        """
        return await self.filter(transaction_id=transaction_id)

    async def get_matched(self, limit: Optional[int] = None) -> List[Match]:
        """
        Get all successful matches.

        Args:
            limit: Maximum number to return

        Returns:
            List of matched records
        """
        query = (
            select(self.model)
            .where(self.model.matched.is_(True))
            .order_by(desc(self.model.confidence))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_unmatched(self, limit: Optional[int] = None) -> List[Match]:
        """
        Get all unmatched records.

        Args:
            limit: Maximum number to return

        Returns:
            List of unmatched records
        """
        query = (
            select(self.model)
            .where(self.model.matched.is_(False))
            .order_by(desc(self.model.matched_at))
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_confidence_threshold(self, min_confidence: float) -> List[Match]:
        """
        Get matches above a confidence threshold.

        Args:
            min_confidence: Minimum confidence score (0-1)

        Returns:
            List of matches
        """
        query = (
            select(self.model)
            .where(self.model.confidence >= min_confidence)
            .order_by(desc(self.model.confidence))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_matched_email_ids(self) -> List[int]:
        """
        Get IDs of all emails that have been matched.

        Returns:
            List of email IDs that have matches
        """
        query = select(self.model.email_id).distinct()
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_matched_transaction_ids(self) -> List[int]:
        """
        Get IDs of all transactions that have been matched.

        Returns:
            List of transaction IDs that have matches
        """
        query = select(self.model.transaction_id).distinct().where(
            self.model.transaction_id.is_not(None)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_review(self, limit: Optional[int] = None) -> List[Match]:
        """
        Get matches pending manual review.

        Args:
            limit: Maximum number to return

        Returns:
            List of matches needing review
        """
        query = (
            select(self.model)
            .where(self.model.status == "review")
            .order_by(self.model.matched_at.asc())
        )
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_match(
        self,
        email_id: int,
        transaction_id: Optional[int],
        matched: bool,
        confidence: float,
        match_method: Optional[str] = None,
        match_details: Optional[str] = None,
        alternative_matches: Optional[str] = None,
    ) -> Match:
        """
        Create a new match record.

        Args:
            email_id: Email ID
            transaction_id: Transaction ID (None if unmatched)
            matched: Whether a match was found
            confidence: Confidence score (0-1)
            match_method: Matching method used
            match_details: JSON details
            alternative_matches: JSON array of alternatives

        Returns:
            Created match instance
        """
        return await self.create(
            email_id=email_id,
            transaction_id=transaction_id,
            matched=matched,
            confidence=confidence,
            match_method=match_method,
            match_details=match_details,
            alternative_matches=alternative_matches,
            status="pending" if matched else "unmatched",
        )

    async def update_match_status(
        self,
        match_id: int,
        status: str,
        reviewed_by: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> Optional[Match]:
        """
        Update match status and review information.

        Args:
            match_id: Match ID
            status: New status
            reviewed_by: Reviewer identifier
            review_notes: Review notes

        Returns:
            Updated match instance
        """
        update_data = {"status": status, "reviewed_at": datetime.now(timezone.utc)}
        if reviewed_by:
            update_data["reviewed_by"] = reviewed_by
        if review_notes:
            update_data["review_notes"] = review_notes

        return await self.update(match_id, **update_data)

    async def count_matched(self) -> int:
        """Get count of successful matches."""
        return await self.count(matched=True)

    async def count_unmatched(self) -> int:
        """Get count of unmatched records."""
        return await self.count(matched=False)

    async def get_match_statistics(self) -> dict:
        """
        Get matching statistics.

        Returns:
            Dictionary with match counts and averages
        """
        from sqlalchemy import func

        # Count queries
        total = await self.count()
        matched = await self.count_matched()
        unmatched = await self.count_unmatched()
        pending_review = await self.count(status="review")

        # Average confidence
        avg_query = select(func.avg(self.model.confidence)).where(
            self.model.matched.is_(True)
        )
        result = await self.session.execute(avg_query)
        avg_confidence = result.scalar() or 0.0

        return {
            "total": total,
            "matched": matched,
            "unmatched": unmatched,
            "pending_review": pending_review,
            "average_confidence": float(avg_confidence),
            "match_rate": (matched / total * 100) if total > 0 else 0.0,
        }
