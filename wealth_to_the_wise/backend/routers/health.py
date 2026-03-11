# filepath: backend/routers/health.py
"""
Health & readiness endpoints.

GET /health        →  Lightweight liveness probe (always fast)
GET /health/ready  →  Deep readiness probe (verifies DB connection)
GET /health/metrics → In-memory latency / error counters

Used by load balancers, Docker HEALTHCHECK, Railway, and uptime monitors.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.rate_limit import limiter
from backend.schemas import HealthResponse

logger = logging.getLogger("tubevo.backend.health")

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
@limiter.limit("120/minute")
async def health_check(request: Request) -> HealthResponse:
    """Lightweight liveness probe — does NOT hit the database."""
    from backend.config import get_settings

    settings = get_settings()
    env = "development" if settings.debug else "production"
    return HealthResponse(status="ok", version=request.app.version, environment=env)


@router.get("/health/ready")
@limiter.limit("30/minute")
async def readiness_check(request: Request) -> JSONResponse:
    """Deep readiness probe — verifies the database is reachable.

    Returns 200 if all dependencies are healthy, 503 if any are down.
    Railway / load balancers should use this for routing decisions.
    """
    from backend.config import get_settings
    from backend.database import get_db

    settings = get_settings()
    env = "development" if settings.debug else "production"
    checks: dict = {"database": "unknown"}

    # ── Database connectivity check ──
    try:
        t0 = time.monotonic()
        async for db in get_db():
            result = await db.execute(text("SELECT 1"))
            result.scalar()  # consume the result
        db_latency_ms = round((time.monotonic() - t0) * 1000, 1)
        checks["database"] = "ok"
        checks["db_latency_ms"] = db_latency_ms
    except Exception as exc:
        logger.error("Readiness probe: database unreachable — %s", exc)
        checks["database"] = "unreachable"
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "version": request.app.version,
                "environment": env,
                "checks": checks,
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "version": request.app.version,
            "environment": env,
            "checks": checks,
        },
    )


@router.get("/health/metrics")
@limiter.limit("30/minute")
async def health_metrics(request: Request) -> dict:
    """Return in-memory p50/p95 latency, request count, and error rate.

    Intended for internal dashboards and alerting.
    No auth required — data contains no PII, just aggregate counters.
    """
    from backend.middleware import get_metrics

    return get_metrics()
