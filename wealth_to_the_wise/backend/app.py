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
from backend.database import create_tables, dispose_engine, async_session_factory
from backend.middleware import RequestLoggingMiddleware
from backend.rate_limit import limiter
from backend.routers import (
    api_keys, auth, admin, billing, health, schedules, videos, waitlist, youtube,
    # Empire OS routers (Phase 0 — scaffold only, gated by feature flags)
    channels, competitors, niche_intel, revenue, thumb_experiments, trend_radar, voice_clones,
    insights, teams, referrals,
)
from backend.scheduler_worker import scheduler_loop
from backend.analytics_worker import analytics_loop
from backend.feature_flags import (
    FF_COMPETITOR_SPY, FF_NICHE_INTEL, FF_REVENUE, FF_THUMB_AB, FF_VOICE_CLONE,
    FF_TREND_RADAR,
    is_globally_enabled,
)

logger = logging.getLogger("tubevo.backend.app")


# ── Phase 2: Zombie-job sweep on startup ─────────────────────────────

async def _sweep_stale_jobs_on_startup() -> None:
    """Mark every ``generating`` video as ``failed`` on server startup.

    After a Railway redeploy or container crash, any in-progress pipeline
    tasks are dead — the asyncio tasks they ran in no longer exist.
    Rather than waiting for a per-user status poll to discover this, we
    sweep them immediately so the dashboard shows the correct state.

    Also sweeps TrendAlerts stuck in ``generating`` status — without this
    they would block the user's in-flight guard indefinitely.
    """
    from datetime import datetime, timezone
    from sqlalchemy import update
    from backend.models import VideoRecord, TrendAlert

    try:
        async with async_session_factory() as db:
            # ── Sweep stale VideoRecords ─────────────────────────────
            stmt = (
                update(VideoRecord)
                .where(VideoRecord.status == "generating")
                .values(
                    status="failed",
                    error_message=(
                        "Video generation was interrupted by a server restart. "
                        "Please try again."
                    ),
                    error_category="timeout",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            result = await db.execute(stmt)
            video_affected = getattr(result, "rowcount", 0)

            # ── Sweep queued bulk-batch videos left orphaned by crash ─
            queued_stmt = (
                update(VideoRecord)
                .where(VideoRecord.status == "queued")
                .values(
                    status="failed",
                    error_message=(
                        "Bulk batch was interrupted by a server restart. "
                        "Please re-submit the batch."
                    ),
                    error_category="timeout",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            queued_result = await db.execute(queued_stmt)
            queued_affected = getattr(queued_result, "rowcount", 0)

            # ── Sweep stale TrendAlerts stuck in "generating" ────────
            alert_stmt = (
                update(TrendAlert)
                .where(TrendAlert.status == "generating")
                .values(
                    status="failed",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            alert_result = await db.execute(alert_stmt)
            alert_affected = getattr(alert_result, "rowcount", 0)

            await db.commit()

            if video_affected or alert_affected or queued_affected:
                logger.warning(
                    "🧹 Startup sweep: marked %d stale videos + %d queued bulk videos + %d stale trend alerts as failed",
                    video_affected, queued_affected, alert_affected,
                )
            else:
                logger.info("🧹 Startup sweep: no stale jobs found")
    except Exception:
        logger.exception("Startup sweep failed (non-fatal)")


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

        # ── Encryption canary — fail fast if JWT_SECRET_KEY changed ──
        from backend.encryption import encrypt as _enc, decrypt as _dec
        _canary = "tubevo-encryption-canary"
        if _dec(_enc(_canary)) != _canary:
            raise RuntimeError(
                "FATAL: Encryption round-trip failed. "
                "JWT_SECRET_KEY may have changed — all encrypted API keys "
                "and OAuth tokens are now unreadable. Restore the original "
                "key or re-encrypt all stored secrets."
            )
        logger.info("🔐 Encryption canary passed")

        # ── Phase 2: Sweep stale "generating" jobs left over from a
        # previous deploy / container restart (zombie protection) ─────
        await _sweep_stale_jobs_on_startup()

        # ── Empire OS: Backfill default channels for legacy users ────
        try:
            from backend.workers.channel_migration import backfill_default_channels
            await backfill_default_channels()
        except Exception:
            logger.warning("Channel backfill failed (non-fatal)")

        # ── Phase 3: Clean up old per-run output directories ─────────
        try:
            from backend.routers.videos import _cleanup_old_output_dirs
            await _cleanup_old_output_dirs(max_age_hours=24)
        except Exception:
            logger.warning("Startup: old output dir cleanup failed (non-fatal)")

        # Start the background scheduler worker
        scheduler_task = asyncio.create_task(scheduler_loop())
        logger.info("🕐 Scheduler worker task created")

        # Start the background analytics worker
        analytics_task = asyncio.create_task(analytics_loop())
        logger.info("📊 Analytics worker task created")

        # ── Empire OS workers (conditionally started behind feature flags) ──
        empire_tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

        if is_globally_enabled(FF_NICHE_INTEL):
            from backend.workers.niche_worker import niche_loop
            empire_tasks.append(asyncio.create_task(niche_loop()))
            logger.info("🔍 Niche intelligence worker started")

        if is_globally_enabled(FF_REVENUE):
            from backend.workers.revenue_worker import revenue_loop
            empire_tasks.append(asyncio.create_task(revenue_loop()))
            logger.info("💰 Revenue worker started")

        if is_globally_enabled(FF_THUMB_AB):
            from backend.workers.thumb_ab_worker import thumb_ab_loop
            empire_tasks.append(asyncio.create_task(thumb_ab_loop()))
            logger.info("🖼️ Thumbnail A/B worker started")

        if is_globally_enabled(FF_COMPETITOR_SPY):
            from backend.workers.competitor_worker import competitor_loop
            empire_tasks.append(asyncio.create_task(competitor_loop()))
            logger.info("🕵️ Competitor monitoring worker started")

        if is_globally_enabled(FF_VOICE_CLONE):
            from backend.workers.voice_clone_worker import voice_clone_loop
            empire_tasks.append(asyncio.create_task(voice_clone_loop()))
            logger.info("🎙️ Voice clone worker started")

        if is_globally_enabled(FF_TREND_RADAR):
            from backend.workers.trend_radar_worker import trend_radar_loop
            empire_tasks.append(asyncio.create_task(trend_radar_loop()))
            logger.info("📡 Trend Radar worker started")

        if not empire_tasks:
            logger.info("⚡ Empire OS: no workers enabled (all feature flags off)")

        yield

        # ── Shutdown ──
        scheduler_task.cancel()
        analytics_task.cancel()
        for t in empire_tasks:
            t.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        try:
            await analytics_task
        except asyncio.CancelledError:
            pass
        for t in empire_tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        await dispose_engine()
        logger.info("Backend shutting down.")

    # Disable docs/OpenAPI schema in production — don't expose the full API
    # surface to attackers.  Keep them enabled for local development.
    _is_prod = settings.environment.lower() == "production"

    app = FastAPI(
        title=settings.app_name,
        description="SaaS backend for automated YouTube content pipelines.",
        version="0.1.1",
        docs_url=None if _is_prod else "/docs",
        redoc_url=None if _is_prod else "/redoc",
        openapi_url=None if _is_prod else "/openapi.json",
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
    app.include_router(admin.router)
    app.include_router(api_keys.router)
    app.include_router(billing.router)
    app.include_router(videos.router)
    app.include_router(youtube.router)
    app.include_router(schedules.router)
    app.include_router(waitlist.router)

    # ── Empire OS routers (all gated by feature flags at router level) ──
    app.include_router(channels.router)
    app.include_router(niche_intel.router)
    app.include_router(revenue.router)
    app.include_router(thumb_experiments.router)
    app.include_router(competitors.router)
    app.include_router(voice_clones.router)
    app.include_router(trend_radar.router)
    app.include_router(insights.router)
    app.include_router(teams.router)
    app.include_router(referrals.router)

    return app


# ── Module-level app instance (for `uvicorn backend.app:app`) ────────
app = create_app()
