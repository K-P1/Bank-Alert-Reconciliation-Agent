from __future__ import annotations

from fastapi import FastAPI

from app.a2a.router import router as a2a_router
from app.transactions.router import router as transactions_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_middleware


settings = get_settings()
configure_logging(settings.ENV)

app = FastAPI(title="Bank Alert Reconciliation Agent", version="0.1.0")
app.middleware("http")(request_id_middleware)
app.include_router(a2a_router)
app.include_router(transactions_router)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "env": settings.ENV}
