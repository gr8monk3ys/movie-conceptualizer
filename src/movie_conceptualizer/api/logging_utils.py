"""Logging utilities for structured request/worker logging."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time
from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_metrics_lock = Lock()
_request_count = 0
_request_status_counts: Counter[int] = Counter()
_request_latency_sum_ms = 0.0
_request_latency_count = 0


def get_request_id() -> str | None:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """JSON log formatter with request correlation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


class RequestIdFilter(logging.Filter):
    """Inject request ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
    """Configure logging format and handlers based on environment."""
    level_name = os.environ.get("MOVIECON_LOG_LEVEL", "INFO").upper()
    log_format = os.environ.get("MOVIECON_LOG_FORMAT", "json").lower()

    root_logger = logging.getLogger()
    root_logger.setLevel(level_name)

    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())

    if log_format == "text":
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s request_id=%(request_id)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        formatter = JsonFormatter()

    handler.setFormatter(formatter)

    # Replace existing handlers to avoid duplicate logs.
    root_logger.handlers = [handler]


class RequestLogger:
    """Helper for request timing metrics."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def log_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        record_request_metrics(status_code, duration_ms)
        self._logger.info(
            "request_completed",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )


def record_request_metrics(status_code: int, duration_ms: float) -> None:
    """Record in-memory request metrics."""
    global _request_count, _request_latency_sum_ms, _request_latency_count
    with _metrics_lock:
        _request_count += 1
        _request_status_counts[status_code] += 1
        _request_latency_sum_ms += duration_ms
        _request_latency_count += 1


def get_request_metrics() -> dict[str, Any]:
    """Get a snapshot of in-memory request metrics."""
    with _metrics_lock:
        avg_latency = (
            _request_latency_sum_ms / _request_latency_count if _request_latency_count else 0.0
        )
        return {
            "count": _request_count,
            "status_counts": dict(_request_status_counts),
            "avg_latency_ms": round(avg_latency, 2),
        }


def now_ms() -> float:
    return time.perf_counter() * 1000.0
