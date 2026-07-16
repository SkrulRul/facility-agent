from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Every attribute a bare LogRecord carries before any `extra=` is merged in —
# used to separate caller-supplied structured fields from stdlib's own bookkeeping.
_RESERVED_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys())


class _CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key != "correlation_id":
                payload[key] = value
        if record.exc_info:
            exc_type, exc_value, _traceback = record.exc_info
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent root-logger setup: one stdout handler, JSON formatter, correlation filter.

    Idempotent so it's safe to call both from app/main.py at import time and
    from test setup without accumulating duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_CorrelationIdFilter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def new_correlation_id() -> Generator[str]:
    """Bind a fresh correlation id for the duration of the block.

    For call sites with no ASGI request/response cycle to hang middleware off
    of (MCP tool invocations) — see CorrelationIdMiddleware for the HTTP path.
    """
    correlation_id = uuid4().hex
    token = _correlation_id.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _correlation_id.reset(token)


_middleware_logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns a fresh correlation id to every request and echoes it on the response.

    Also the catch-all for exceptions no app-level handler mapped to a status
    code: Starlette's ServerErrorMiddleware sits *outside* user middleware and
    always re-raises after building its response (see its `__call__`), which
    would unwind past this middleware before it can stamp X-Request-ID or see
    a live correlation_id contextvar — so an app.main-level `Exception`
    handler can't produce a correlated response. Building the fallback 500
    here, before the exception leaves this middleware, is what makes it work.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        with new_correlation_id() as correlation_id:
            try:
                response = await call_next(request)
            except Exception as exc:
                _middleware_logger.error(
                    "Unhandled exception",
                    exc_info=True,
                    extra={"exception_type": type(exc).__name__},
                )
                response = JSONResponse(
                    status_code=500, content={"detail": "internal server error"}
                )
            response.headers["X-Request-ID"] = correlation_id
            return response
