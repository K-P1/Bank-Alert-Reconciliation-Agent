"""Database initialization utilities."""

import asyncio
import re
from app.db.base import engine, Base
from app.core.config import get_settings
import structlog

# Import all models to register them with Base.metadata
from app.db.models import Email, Transaction, Match, Log, Config  # noqa: F401

logger = structlog.get_logger(__name__)


def sanitize_db_url(db_url: str) -> str:
    """
    Sanitize database URL by hiding username and password.
    
    Converts: postgresql+asyncpg://user:pass@localhost:5432/db
    To:       postgresql+asyncpg://***:***@localhost:5432/db
    """
    # Pattern matches: scheme://username:password@host...
    pattern = r"(.*://)[^:]+:[^@]+(@.*)"
    return re.sub(pattern, r"\1***:***\2", db_url)


async def create_tables():
    """Create all database tables."""
    settings = get_settings()
    db_url = settings.DATABASE_URL or "sqlite+aiosqlite:///./bankagent.db"
    logger.info(f"📊 Target database: {sanitize_db_url(db_url)}")
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def drop_tables():
    """Drop all database tables (use with caution!)."""
    settings = get_settings()
    db_url = settings.DATABASE_URL or "sqlite+aiosqlite:///./bankagent.db"
    logger.warning(f"📊 Target database: {sanitize_db_url(db_url)}")
    logger.warning("Dropping all database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped")


async def reset_database():
    """Reset database by dropping and recreating all tables."""
    settings = get_settings()
    if settings.ENV == "production":
        raise RuntimeError("Cannot reset database in production environment!")

    db_url = settings.DATABASE_URL or "sqlite+aiosqlite:///./bankagent.db"
    logger.warning("=" * 70)
    logger.warning("🔄 RESETTING DATABASE")
    logger.warning(f"📊 Target database: {sanitize_db_url(db_url)}")
    logger.warning("=" * 70)
    
    await drop_tables()
    await create_tables()
    
    # Dispose engine to ensure clean state
    await engine.dispose()
    
    logger.info("=" * 70)
    logger.info("✅ Database reset complete")
    logger.info("=" * 70)
    logger.warning("⚠️  IMPORTANT: Restart any running servers to pick up the reset!")
    logger.warning("   Stop the uvicorn/FastAPI server and restart it.")


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
        # Show target database before confirmation
        settings = get_settings()
        db_url = settings.DATABASE_URL or "sqlite+aiosqlite:///./bankagent.db"
        print("=" * 70)
        print(f"📊 Target database: {sanitize_db_url(db_url)}")
        print("=" * 70)
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
