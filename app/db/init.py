"""Database initialization utilities."""

import asyncio
from app.db.base import engine, Base
from app.core.config import get_settings
import structlog

logger = structlog.get_logger(__name__)


async def create_tables():
    """Create all database tables."""
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def drop_tables():
    """Drop all database tables (use with caution!)."""
    logger.warning("Dropping all database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped")


async def reset_database():
    """Reset database by dropping and recreating all tables."""
    settings = get_settings()
    if settings.ENV == "production":
        raise RuntimeError("Cannot reset database in production environment!")

    logger.warning("Resetting database...")
    await drop_tables()
    await create_tables()
    logger.info("Database reset complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.db.init [create|drop|reset]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        asyncio.run(create_tables())
    elif command == "drop":
        response = input("WARNING: This will drop all tables. Continue? (yes/no): ")
        if response.lower() == "yes":
            asyncio.run(drop_tables())
        else:
            print("Cancelled.")
    elif command == "reset":
        response = input(
            "WARNING: This will drop and recreate all tables. Continue? (yes/no): "
        )
        if response.lower() == "yes":
            asyncio.run(reset_database())
        else:
            print("Cancelled.")
    else:
        print(f"Unknown command: {command}")
        print("Available commands: create, drop, reset")
        sys.exit(1)
