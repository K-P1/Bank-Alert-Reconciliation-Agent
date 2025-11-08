import sys
from pathlib import Path
import pytest
import pytest_asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

# Ensure project root is on sys.path so `import app` works when running pytest from root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base  # noqa: E402

# Force test database URL before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def override_database_url():
    """Override DATABASE_URL environment variable for all tests."""
    import os

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    yield
    # Cleanup after tests (optional)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Module-level variables for test database
_test_engine = None
_test_session_factory = None
_engine_initialized = False


async def init_test_db():
    """Initialize test database engine and tables once."""
    global _test_engine, _test_session_factory, _engine_initialized

    if _engine_initialized:
        return

    # Force SQLite for tests
    test_db_url = "sqlite+aiosqlite:///:memory:"

    # Create async engine for tests
    _test_engine = create_async_engine(
        test_db_url,
        echo=False,
        future=True,
    )

    # Create all tables
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    _test_session_factory = async_sessionmaker(
        _test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    _engine_initialized = True

    # CRITICAL: Patch app.db.base to use test engine and session factory
    import app.db.base

    app.db.base.engine = _test_engine
    app.db.base.AsyncSessionLocal = _test_session_factory


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """
    Provide a clean database session factory for each test.
    """
    await init_test_db()
    yield _test_session_factory


@pytest_asyncio.fixture
async def db_session(test_db):
    """Get a database session for a test."""
    async with test_db() as session:
        yield session
        await session.rollback()  # Ensure clean state after test


async def get_test_db() -> AsyncGenerator[AsyncSession, None]:
    """Test database dependency override."""
    await init_test_db()

    if _test_session_factory is None:
        raise RuntimeError("Test session factory not initialized")

    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
