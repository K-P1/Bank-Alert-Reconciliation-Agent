"""Base repository class with common CRUD operations."""

from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common CRUD operations for all models.

    This class implements the repository pattern, providing a clean
    abstraction over database operations with transaction support.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def create(self, **kwargs) -> ModelType:
        """
        Create a new record.

        Args:
            **kwargs: Field values for the new record

        Returns:
            Created model instance
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """
        Get a record by ID.

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore
        )
        return result.scalar_one_or_none()

    async def get_by_field(self, field_name: str, value: Any) -> Optional[ModelType]:
        """
        Get a record by a specific field value.

        Args:
            field_name: Name of the field to search
            value: Value to search for

        Returns:
            Model instance or None if not found
        """
        field = getattr(self.model, field_name)
        result = await self.session.execute(select(self.model).where(field == value))
        return result.scalar_one_or_none()

    async def get_all(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[ModelType]:
        """
        Get all records with optional pagination.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        query = select(self.model)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def filter(self, **filters) -> List[ModelType]:
        """
        Filter records by field values.

        Args:
            **filters: Field name and value pairs

        Returns:
            List of matching model instances
        """
        query = select(self.model)
        for field_name, value in filters.items():
            field = getattr(self.model, field_name)
            query = query.where(field == value)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """
        Update a record by ID.

        Args:
            id: Record ID
            **kwargs: Fields to update with their new values

        Returns:
            Updated model instance or None if not found
        """
        await self.session.execute(
            update(self.model).where(self.model.id == id).values(**kwargs)  # type: ignore
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: int) -> bool:
        """
        Delete a record by ID.

        Args:
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)  # type: ignore
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0  # type: ignore

    async def count(self, **filters) -> int:
        """
        Count records matching the given filters.

        Args:
            **filters: Field name and value pairs

        Returns:
            Number of matching records
        """
        from sqlalchemy import func

        query = select(func.count(self.model.id))  # type: ignore
        for field_name, value in filters.items():
            field = getattr(self.model, field_name)
            query = query.where(field == value)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def exists(self, **filters) -> bool:
        """
        Check if any records exist matching the given filters.

        Args:
            **filters: Field name and value pairs

        Returns:
            True if at least one matching record exists
        """
        count = await self.count(**filters)
        return count > 0
