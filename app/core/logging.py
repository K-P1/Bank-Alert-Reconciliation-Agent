from __future__ import annotations

import logging
import sys
import time
import uuid
from typing import Any, Dict

import structlog
from fastapi import Request


def _add_log_level(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    event_dict["level"] = method_name
    return event_dict


def configure_logging(env: str = "development") -> None:
    """Configure structlog for clean, readable console logs to stdout."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Configure standard logging to go through structlog
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    # Use ConsoleRenderer for human-readable output instead of JSON
    # This provides clean, colored output perfect for reading logs in console
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Middleware that injects a request_id and basic latency metrics into logs."""
    start = time.perf_counter()

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(
        request_id=request_id, path=str(request.url.path)
    )

    response = None
    try:
        response = await call_next(request)
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger = structlog.get_logger("request")
        logger.info(
            "request.completed",
            method=request.method,
            status=getattr(response, "status_code", 0) if response else 500,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()

    if response:
        response.headers["x-request-id"] = request_id
    return response
