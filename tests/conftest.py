import sys
import os
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Ensure project root is on sys.path so `import app` works when running pytest from root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.core.config import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Create a test database and clean it up after each test.
    Uses TEST_DATABASE_URL if available, otherwise uses in-memory SQLite.
    """
    settings = get_settings()
    
    # Use test database URL or fallback to in-memory SQLite
    test_db_url = settings.TEST_DATABASE_URL or "sqlite+aiosqlite:///:memory:"
    
    # Create async engine for tests
    engine = create_async_engine(
        test_db_url,
        echo=False,
        future=True,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session factory
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    yield async_session
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_db):
    """Get a database session for a test."""
    async with test_db() as session:
        yield session
