from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.a2a.router import router as a2a_router
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
    logger.info("Starting Bank Alert Reconciliation Agent...")

    # Initialize email fetcher if IMAP is configured
    if all([settings.IMAP_HOST, settings.IMAP_USER, settings.IMAP_PASS]):
        try:
            email_config = EmailConfig.from_settings(settings)
            fetcher = EmailFetcher(settings, email_config)
            set_fetcher(fetcher)

            # Start background polling if enabled
            if email_config.fetcher.enabled and email_config.fetcher.start_immediately:
                await fetcher.start()
                logger.info("Email fetcher started automatically")
            else:
                logger.info("Email fetcher initialized (not auto-started)")

        except Exception as e:
            logger.error(f"Failed to initialize email fetcher: {e}")
    else:
        logger.warning("IMAP settings not configured, email fetcher disabled")

    yield

    # Shutdown
    logger.info("Shutting down Bank Alert Reconciliation Agent...")

    # Stop email fetcher if running
    from app.emails.router import _fetcher

    if _fetcher:
        await _fetcher.stop()
        logger.info("Email fetcher stopped")


app = FastAPI(
    title="Bank Alert Reconciliation Agent", version="0.1.0", lifespan=lifespan
)
app.middleware("http")(request_id_middleware)
app.include_router(a2a_router)
app.include_router(transactions_router)
app.include_router(emails_router)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "env": settings.ENV}
