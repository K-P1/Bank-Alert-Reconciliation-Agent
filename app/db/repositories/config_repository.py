"""Config repository with specialized queries."""

from typing import Optional, List, Any
import json

from app.db.models.config import Config
from app.db.repository import BaseRepository


class ConfigRepository(BaseRepository[Config]):
    """Repository for Config model with specialized queries."""

    async def get_by_key(self, key: str) -> Optional[Config]:
        """Get a config by key.

        Args:
            key: Unique configuration key

        Returns:
            Config instance or None if not found
        """
        return await self.get_by_field("key", key)

    async def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a config value parsed to its correct type.

        Automatically converts the stored string value to the appropriate
        Python type based on the config's value_type field.

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

        Creates a new config entry if the key doesn't exist, or updates
        the existing one. Automatically converts the value to string
        for storage and handles JSON serialization for complex types.

        Args:
            key: Unique configuration key
            value: Configuration value (any type)
            value_type: Data type hint ("string", "int", "float", "bool", "json")
            description: Human-readable description
            category: Grouping category (e.g., "matching", "email")
            is_sensitive: Whether contains sensitive data (affects logging)
            is_editable: Whether can be modified via UI/API
            updated_by: User/system identifier for audit trail

        Returns:
            The created or updated Config instance
        """
        # Convert value to string
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

        Useful for retrieving related configuration settings by functional area.

        Args:
            category: Configuration category (e.g., "matching", "email", "retention")

        Returns:
            List of Config instances in the specified category
        """
        return await self.filter(category=category)

    async def get_editable(self) -> List[Config]:
        """Get all editable configs.

        Returns configs that can be modified via UI/API, excluding
        system-only or read-only configuration settings.

        Returns:
            List of editable Config instances
        """
        return await self.filter(is_editable=True)

    async def get_all_as_dict(self, category: Optional[str] = None) -> dict:
        """
        Get all configs as a dictionary (key -> value).

        Convenient method for loading multiple configuration values at once.
        Values are automatically converted to their proper types.

        Args:
            category: Optional category filter to limit results

        Returns:
            Dictionary mapping config keys to their typed values
        """
        if category:
            configs = await self.get_by_category(category)
        else:
            configs = await self.get_all()

        return {config.key: config.get_typed_value() for config in configs}

    async def delete_by_key(self, key: str) -> bool:
        """
        Delete a config by key.

        Permanently removes a configuration setting from the database.
        Use with caution as this cannot be undone.

        Args:
            key: Unique configuration key to delete

        Returns:
            True if the config was found and deleted, False if not found
        """
        config = await self.get_by_key(key)
        if config:
            return await self.delete(config.id)
        return False
