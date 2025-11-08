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
        
        Supports comparison operators using double underscore syntax:
        - field__lt: less than
        - field__lte: less than or equal
        - field__gt: greater than
        - field__gte: greater than or equal
        - field__ne: not equal
        - field (no suffix): equal

        Args:
            **filters: Field name and value pairs

        Returns:
            List of matching model instances
            
        Examples:
            # Get transactions with amount > 100
            await repo.filter(amount__gt=100)
            
            # Get logs before a certain timestamp
            await repo.filter(timestamp__lt=cutoff_date)
        """
        query = select(self.model)
        query = self._apply_filters(query, filters)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _apply_filters(self, query, filters: dict):
        """
        Apply filters to a query with comparison operator support.

        Args:
            query: SQLAlchemy query
            filters: Field name and value pairs with optional comparison operators

        Returns:
            Modified query
        """
        for filter_key, value in filters.items():
            # Parse field name and operator
            if "__" in filter_key:
                field_name, operator = filter_key.rsplit("__", 1)
            else:
                field_name = filter_key
                operator = "eq"

            field = getattr(self.model, field_name)

            # Apply comparison operator
            if operator == "eq":
                query = query.where(field == value)
            elif operator == "ne":
                query = query.where(field != value)
            elif operator == "lt":
                query = query.where(field < value)
            elif operator == "lte":
                query = query.where(field <= value)
            elif operator == "gt":
                query = query.where(field > value)
            elif operator == "gte":
                query = query.where(field >= value)
            else:
                # Fallback to equality for unknown operators
                query = query.where(field == value)

        return query

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

    async def delete_all(self, **filters) -> int:
        """
        Delete all records matching the given filters.
        If no filters provided, deletes ALL records (use with caution!).

        Args:
            **filters: Field name and value pairs to filter deletion

        Returns:
            Number of records deleted
        """
        query = delete(self.model)
        
        # Apply filters if provided
        if filters:
            query = self._apply_filters_to_delete(query, filters)
        
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount or 0  # type: ignore

    def _apply_filters_to_delete(self, query, filters: dict):
        """
        Apply filters to a delete query.

        Args:
            query: SQLAlchemy delete query
            filters: Field name and value pairs with optional comparison operators

        Returns:
            Modified query
        """
        for filter_key, value in filters.items():
            # Parse field name and operator
            if "__" in filter_key:
                field_name, operator = filter_key.rsplit("__", 1)
            else:
                field_name = filter_key
                operator = "eq"

            field = getattr(self.model, field_name)

            # Apply comparison operator
            if operator == "eq":
                query = query.where(field == value)
            elif operator == "ne":
                query = query.where(field != value)
            elif operator == "lt":
                query = query.where(field < value)
            elif operator == "lte":
                query = query.where(field <= value)
            elif operator == "gt":
                query = query.where(field > value)
            elif operator == "gte":
                query = query.where(field >= value)
            else:
                # Fallback to equality for unknown operators
                query = query.where(field == value)

        return query

    async def count(self, **filters) -> int:
        """
        Count records matching the given filters.
        
        Supports comparison operators using double underscore syntax:
        - field__lt: less than
        - field__lte: less than or equal
        - field__gt: greater than
        - field__gte: greater than or equal
        - field__ne: not equal
        - field (no suffix): equal

        Args:
            **filters: Field name and value pairs

        Returns:
            Number of matching records
            
        Examples:
            # Count logs older than cutoff date
            await repo.count(timestamp__lt=cutoff_date)
        """
        from sqlalchemy import func

        query = select(func.count(self.model.id))  # type: ignore
        query = self._apply_filters(query, filters)

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
