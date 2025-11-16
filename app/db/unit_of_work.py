"""Unit of Work pattern for managing database transactions."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.models import Email, Transaction, Match, Log, Config
from app.db.repositories import (
    EmailRepository,
    TransactionRepository,
    MatchRepository,
    LogRepository,
    ConfigRepository,
)


class UnitOfWork:
    """
    Unit of Work pattern implementation for managing database transactions.

    This class provides a single entry point for all repository operations
    and ensures that all operations within a context share the same database
    session and transaction.

    Usage:
        async with UnitOfWork() as uow:
            email = await uow.emails.get_by_id(1)
            transaction = await uow.transactions.get_by_id(1)
            await uow.matches.create_match(
                email_id=email.id,
                transaction_id=transaction.id,
                matched=True,
                confidence=0.95
            )
            await uow.commit()
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        """
        Initialize Unit of Work.

        Args:
            session: Optional existing session (useful for testing)
        """
        self._session = session
        self._owned_session = session is None

        # Repositories (initialized in __aenter__)
        self.emails: EmailRepository = None  # type: ignore
        self.transactions: TransactionRepository = None  # type: ignore
        self.matches: MatchRepository = None  # type: ignore
        self.logs: LogRepository = None  # type: ignore
        self.config: ConfigRepository = None  # type: ignore

    async def __aenter__(self):
        """Enter async context manager."""
        if self._owned_session:
            self._session = AsyncSessionLocal()

        # Initialize repositories with the session
        assert self._session is not None, "Session must be initialized"
        self.emails = EmailRepository(Email, self._session)
        self.transactions = TransactionRepository(Transaction, self._session)
        self.matches = MatchRepository(Match, self._session)
        self.logs = LogRepository(Log, self._session)
        self.config = ConfigRepository(Config, self._session)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if exc_type is not None:
            # Exception occurred, rollback
            await self.rollback()
        else:
            # No exception, commit if we own the session
            if self._owned_session:
                await self.commit()

        # Close session if we own it
        if self._owned_session and self._session:
            await self._session.close()

    async def commit(self):
        """Commit the current transaction."""
        if self._session:
            await self._session.commit()

    async def rollback(self):
        """Rollback the current transaction."""
        if self._session:
            await self._session.rollback()

    async def refresh(self, instance):
        """
        Refresh an instance from the database.

        Args:
            instance: Model instance to refresh
        """
        if self._session:
            await self._session.refresh(instance)

    async def flush(self):
        """Flush pending changes to the database without committing."""
        if self._session:
            await self._session.flush()
