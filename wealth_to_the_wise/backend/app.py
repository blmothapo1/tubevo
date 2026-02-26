# filepath: backend/app.py
"""
FastAPI application factory for Tubevo SaaS backend.

Item 1: Backend Service
-----------------------
✓ FastAPI app with metadata (title, description, version)
✓ CORS middleware (origins from env var)
✓ Rate limiting via SlowAPI (default 60/min, per-IP)
✓ Request logging middleware (request-id, method, path, status, latency)
✓ Input validation via Pydantic schemas
✓ Centralised exception handling (422 → clean JSON, unexpected → 500)
✓ Env var security via pydantic-settings (no raw os.getenv, secrets never logged)
✓ Logging carried over from Phase 1 (same format, file + console)

Future items will add routers here as they're built:
  Item 2 → /auth/*
  Item 3 → /oauth/youtube/*
  Item 5 → /api/*
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import get_settings, logger as config_logger  # noqa: F401 — triggers logging setup
from backend.database import create_tables, dispose_engine
from backend.middleware import RequestLoggingMiddleware
from backend.rate_limit import limiter
from backend.routers import api_keys, auth, billing, health, schedules, videos, waitlist, youtube
from backend.scheduler_worker import scheduler_loop

logger = logging.getLogger("tubevo.backend.app")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ── Startup ──
        logger.info("═" * 60)
        logger.info("  🚀  %s backend starting", settings.app_name)
        logger.info("       debug=%s  cors=%s  rate_limit=%s",
                     settings.debug, settings.cors_origins, settings.rate_limit_default)
        logger.info("═" * 60)
        await create_tables()

        # Start the background scheduler worker
        scheduler_task = asyncio.create_task(scheduler_loop())
        logger.info("🕐 Scheduler worker task created")

        yield

        # ── Shutdown ──
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await dispose_engine()
        logger.info("Backend shutting down.")

    app = FastAPI(
        title=settings.app_name,
        description="SaaS backend for automated YouTube content pipelines.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # ── Rate Limiting ────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # ── CORS ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ────────────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)

    # ── Exception handlers ───────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Return clean 422 errors instead of FastAPI's verbose default."""
        errors = []
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            errors.append(f"{loc}: {err.get('msg', 'invalid')}")
        return JSONResponse(
            status_code=422,
            content={"detail": "; ".join(errors)},
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch unhandled exceptions so clients always get valid JSON."""
        request_id = getattr(request.state, "request_id", "???")
        logger.exception("[%s] Unhandled exception: %s", request_id, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Check logs for details."},
        )

    # ── Routers ──────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(api_keys.router)
    app.include_router(billing.router)
    app.include_router(videos.router)
    app.include_router(youtube.router)
    app.include_router(schedules.router)
    app.include_router(waitlist.router)

    return app


# ── Module-level app instance (for `uvicorn backend.app:app`) ────────
app = create_app()
