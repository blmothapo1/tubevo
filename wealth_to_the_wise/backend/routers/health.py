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

logger = logging.getLogger("tubevo.backend.health")

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
@limiter.limit("120/minute")
async def health_check(request: Request) -> HealthResponse:
    """Lightweight liveness probe."""
    from backend.config import get_settings

    settings = get_settings()
    env = "development" if settings.debug else "production"
    return HealthResponse(status="ok", version="0.1.0", environment=env)


@router.get("/health/debug-kit")
async def debug_kit(request: Request) -> dict:
    """Temporary debug endpoint — check Kit API key availability on Railway."""
    import os
    from backend.config import get_settings
    settings = get_settings()
    key = settings.kit_api_key

    # Also check raw env vars for any KIT-related vars
    kit_env_vars = {k: v[:4] + "..." for k, v in os.environ.items() if "KIT" in k.upper()}

    return {
        "kit_key_set": bool(key),
        "kit_key_length": len(key) if key else 0,
        "kit_key_prefix": key[:4] + "..." if key and len(key) > 4 else "empty",
        "kit_env_vars_found": kit_env_vars,
        "total_env_var_count": len(os.environ),
    }
