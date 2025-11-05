"""Config repository with specialized queries."""

from typing import Optional, List, Any
import json

from app.db.models.config import Config
from app.db.repository import BaseRepository


class ConfigRepository(BaseRepository[Config]):
    """Repository for Config model with specialized queries."""

    async def get_by_key(self, key: str) -> Optional[Config]:
        """Get a config by key."""
        return await self.get_by_field("key", key)

    async def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a config value parsed to its correct type.

        Args:
            key: Config key
            default: Default value if not found

        Returns:
            Typed config value or default
        """
        config = await self.get_by_key(key)
        if config is None:
            return default
        return config.get_typed_value()

    async def set_value(
        self,
        key: str,
        value: Any,
        value_type: str = "string",
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_sensitive: bool = False,
        is_editable: bool = True,
        updated_by: Optional[str] = None,
    ) -> Config:
        """
        Set a config value (create or update).

        Args:
            key: Config key
            value: Config value
            value_type: Type hint
            description: Description
            category: Category
            is_sensitive: Whether sensitive
            is_editable: Whether editable
            updated_by: Who updated it

        Returns:
            Config instance
        """
        # Convert value to string
        if value_type == "json":
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        existing = await self.get_by_key(key)
        if existing:
            # Update existing
            update_data = {"value": value_str, "value_type": value_type}
            if description is not None:
                update_data["description"] = description
            if category is not None:
                update_data["category"] = category
            if updated_by is not None:
                update_data["updated_by"] = updated_by

            updated = await self.update(existing.id, **update_data)
            assert updated is not None, "Update should return the updated config"
            return updated
        else:
            # Create new
            return await self.create(
                key=key,
                value=value_str,
                value_type=value_type,
                description=description,
                category=category,
                is_sensitive=is_sensitive,
                is_editable=is_editable,
                created_by=updated_by,
            )

    async def get_by_category(self, category: str) -> List[Config]:
        """
        Get all configs in a category.

        Args:
            category: Config category

        Returns:
            List of configs
        """
        return await self.filter(category=category)

    async def get_editable(self) -> List[Config]:
        """Get all editable configs."""
        return await self.filter(is_editable=True)

    async def get_all_as_dict(self, category: Optional[str] = None) -> dict:
        """
        Get all configs as a dictionary (key -> value).

        Args:
            category: Optional category filter

        Returns:
            Dictionary of config key-value pairs
        """
        if category:
            configs = await self.get_by_category(category)
        else:
            configs = await self.get_all()

        return {config.key: config.get_typed_value() for config in configs}

    async def delete_by_key(self, key: str) -> bool:
        """
        Delete a config by key.

        Args:
            key: Config key

        Returns:
            True if deleted
        """
        config = await self.get_by_key(key)
        if config:
            return await self.delete(config.id)
        return False
