from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.a2a.router import router as a2a_router
from app.core.automation import get_automation_service
from app.core.automation_router import router as automation_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware
from app.emails.config import EmailConfig
from app.emails.fetcher import EmailFetcher
from app.emails.router import router as emails_router
from app.emails.router import set_fetcher
from app.transactions.router import router as transactions_router

logger = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings.ENV)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup
    logger.info("=" * 70)
    logger.info("🚀 Starting Bank Alert Reconciliation Agent (BARA)...")
    logger.info(f"Environment: {settings.ENV}")
    logger.info(
        f"Database: {settings.DATABASE_URL.split('/')[-1] if settings.DATABASE_URL else 'Not configured'}"
    )
    logger.info("=" * 70)

    # Initialize email fetcher if IMAP is configured
    if all([settings.IMAP_HOST, settings.IMAP_USER, settings.IMAP_PASS]):
        try:
            logger.info("📧 Initializing email fetcher...")
            email_config = EmailConfig.from_settings(settings)
            fetcher = EmailFetcher(settings, email_config)
            set_fetcher(fetcher)
            logger.info("✓ Email fetcher initialized (not auto-started)")

        except Exception as e:
            logger.error(f"✗ Failed to initialize email fetcher: {e}", exc_info=True)
    else:
        logger.warning("⚠ IMAP settings not configured, email fetcher disabled")

    # Initialize automation service (unified orchestration)
    logger.info("🤖 Initializing automation service...")
    automation = get_automation_service()
    logger.info("✓ Automation service initialized (not auto-started)")
    logger.info("   Use POST /automation/start or A2A 'start automation' command")

    logger.info("=" * 70)
    logger.info("✓ BARA startup complete - Ready to process requests")
    logger.info("=" * 70)

    yield

    # Shutdown
    logger.info("=" * 70)
    logger.info("🛑 Shutting down Bank Alert Reconciliation Agent...")
    logger.info("=" * 70)

    # Stop automation service if running
    automation = get_automation_service()
    if automation._running:
        logger.info("Stopping automation service...")
        await automation.stop()
        logger.info("✓ Automation service stopped")

    # Stop email fetcher if running
    from app.emails.router import _fetcher

    if _fetcher and _fetcher._running:
        logger.info("Stopping email fetcher...")
        await _fetcher.stop()
        logger.info("✓ Email fetcher stopped")

    logger.info("=" * 70)
    logger.info("✓ BARA shutdown complete")
    logger.info("=" * 70)


app = FastAPI(
    title="Bank Alert Reconciliation Agent", version="0.1.0", lifespan=lifespan
)
app.middleware("http")(request_id_middleware)
app.include_router(a2a_router)
app.include_router(automation_router)
app.include_router(transactions_router)
app.include_router(emails_router)


@app.get("/")
def health_check():
    logger.debug("Health check endpoint called")
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    logger.debug(f"Healthz endpoint called (env: {settings.ENV})")
    return {"status": "healthy", "env": settings.ENV}
