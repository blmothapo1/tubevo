# filepath: backend/middleware.py
"""
Custom middleware for the SaaS backend.

- Request-ID injection (every response gets a unique X-Request-ID)
- Request/response logging (mirrors Phase 1 structured log style)
- In-memory p95 latency and failure-rate counters for /health/metrics
"""

from __future__ import annotations

import collections
import logging
import threading
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("tubevo.backend.middleware")


# ── Observability counters ───────────────────────────────────────────
# Thread-safe in-memory counters.  Exposed via GET /health/metrics.
# These are intentionally simple — no Prometheus dependency required.

_metrics_lock = threading.Lock()
_request_count = 0
_error_count = 0                       # 5xx responses
_latency_window: collections.deque[float] = collections.deque(maxlen=500)


def get_metrics() -> dict:
    """Return a snapshot of current observability metrics."""
    with _metrics_lock:
        latencies = sorted(_latency_window)
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        p95_idx = int(len(latencies) * 0.95)
        p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0
        return {
            "total_requests": _request_count,
            "total_5xx": _error_count,
            "error_rate_pct": round((_error_count / _request_count * 100), 2) if _request_count else 0.0,
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "window_size": len(latencies),
        }


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        global _request_count, _error_count

        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request_id to state so downstream handlers can use it
        request.state.request_id = request_id

        logger.info(
            "[%s]  ➜  %s %s",
            request_id,
            request.method,
            request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("[%s]  💥  Unhandled exception on %s %s", request_id, request.method, request.url.path)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[%s]  ✓  %s %s → %d  (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        # ── Update observability counters ────────────────────────────
        with _metrics_lock:
            _request_count += 1
            _latency_window.append(elapsed_ms)
            if response.status_code >= 500:
                _error_count += 1

        response.headers["X-Request-ID"] = request_id
        return response
