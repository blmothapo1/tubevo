# filepath: backend/middleware.py
"""
Custom middleware for the SaaS backend.

- Request-ID injection (every response gets a unique X-Request-ID)
- Request/response logging (mirrors Phase 1 structured log style)
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("tubevo.backend.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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

        response.headers["X-Request-ID"] = request_id
        return response
