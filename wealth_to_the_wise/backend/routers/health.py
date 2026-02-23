# filepath: backend/routers/health.py
"""
Health & readiness endpoint.

GET /health  →  {"status": "ok", "version": "0.1.0", "environment": "development"}

Used by load balancers, Docker HEALTHCHECK, and uptime monitors.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from backend.rate_limit import limiter
from backend.schemas import HealthResponse

logger = logging.getLogger("wealth_to_the_wise.backend.health")

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
@limiter.limit("120/minute")
async def health_check(request: Request) -> HealthResponse:
    """Lightweight liveness probe."""
    from backend.config import get_settings

    settings = get_settings()
    env = "development" if settings.debug else "production"
    return HealthResponse(status="ok", version="0.1.0", environment=env)
