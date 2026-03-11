# filepath: backend/routers/trend_radar.py
"""
Trend Radar router — /api/trends/*

Exposes the Trend Radar feature as a REST API:
  - GET  /api/trends          — List trend alerts (filterable by status)
  - GET  /api/trends/stats    — Quick stats (ready count, today's auto-publishes, etc.)
  - POST /api/trends/scan     — Force a manual trend scan
  - POST /api/trends/{id}/publish   — One-tap publish a ready trend
  - POST /api/trends/{id}/dismiss   — Dismiss a trend
  - POST /api/trends/{id}/regenerate — Re-generate a failed trend
  - GET  /api/trends/settings       — Get user's trend radar settings
  - PUT  /api/trends/settings       — Update settings (autopilot, thresholds, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import async_session_factory, get_db
from backend.encryption import decrypt, decrypt_or_raise
from backend.feature_flags import FF_TREND_RADAR, require_feature
from backend.models import (
    Channel, ContentMemory, OAuthToken, TrendAlert, TrendRadarSettings,
    User, UserApiKeys, UserPreferences, VideoRecord, _new_uuid, _utcnow,
)
from backend.rate_limit import limiter

logger = logging.getLogger("tubevo.backend.trend_radar")

router = APIRouter(
    prefix="/api/trends",
    tags=["Trend Radar"],
    dependencies=[Depends(require_feature(FF_TREND_RADAR))],
)

# ── Schemas ──────────────────────────────────────────────────────────


class TrendAlertResponse(BaseModel):
    id: str
    trend_topic: str
    trend_source: str
    confidence_score: int
    estimated_demand: int
    competition_level: str
    niche: str
    reasoning: str | None = None
    status: str
    generated_title: str | None = None
    script_preview: str | None = None
    thumbnail_path: str | None = None
    video_record_id: str | None = None
    auto_published: bool = False
    error_message: str | None = None
    detected_at: str
    ready_at: str | None = None
    published_at: str | None = None
    created_at: str


class TrendStatsResponse(BaseModel):
    total_detected: int = 0
    total_generating: int = 0
    total_ready: int = 0
    total_published: int = 0
    total_dismissed: int = 0
    total_failed: int = 0
    auto_published_today: int = 0
    autopilot_enabled: bool = False


class TrendSettingsResponse(BaseModel):
    is_enabled: bool = False
    autopilot_enabled: bool = False
    autopilot_min_confidence: int = 80
    autopilot_daily_cap: int = 1
    scan_interval_minutes: int = 360
    min_confidence_threshold: int = 40


class TrendSettingsUpdate(BaseModel):
    is_enabled: bool | None = None
    autopilot_enabled: bool | None = None
    autopilot_min_confidence: int | None = Field(None, ge=40, le=100)
    autopilot_daily_cap: int | None = Field(None, ge=1, le=10)
    scan_interval_minutes: int | None = Field(None, ge=60, le=1440)
    min_confidence_threshold: int | None = Field(None, ge=20, le=90)


# ── Helpers ──────────────────────────────────────────────────────────

def _serialize_alert(alert: TrendAlert) -> dict:
    return {
        "id": alert.id,
        "trend_topic": alert.trend_topic,
        "trend_source": alert.trend_source,
        "confidence_score": alert.confidence_score,
        "estimated_demand": alert.estimated_demand,
        "competition_level": alert.competition_level,
        "niche": alert.niche,
        "reasoning": alert.reasoning,
        "status": alert.status,
        "generated_title": alert.generated_title,
        "script_preview": alert.script_preview,
        "thumbnail_path": alert.thumbnail_path,
        "video_record_id": alert.video_record_id,
        "auto_published": alert.auto_published,
        "error_message": alert.error_message,
        "detected_at": alert.detected_at.isoformat() if alert.detected_at else None,
        "ready_at": alert.ready_at.isoformat() if alert.ready_at else None,
        "published_at": alert.published_at.isoformat() if alert.published_at else None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


async def _get_or_create_settings(db: AsyncSession, user_id: str) -> TrendRadarSettings:
    result = await db.execute(
        select(TrendRadarSettings).where(TrendRadarSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = TrendRadarSettings(
            id=_new_uuid(),
            user_id=user_id,
        )
        db.add(settings)
        await db.flush()
    return settings


# ── GET /api/trends ──────────────────────────────────────────────────

@router.get("")
async def list_trends(
    request: Request,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all trend alerts for the current user."""
    stmt = (
        select(TrendAlert)
        .where(TrendAlert.user_id == current_user.id)
        .order_by(TrendAlert.created_at.desc())
        .limit(50)
    )

    if status_filter:
        valid_statuses = {"detected", "scanning", "generating", "ready", "published", "dismissed", "failed"}
        statuses = [s.strip() for s in status_filter.split(",") if s.strip() in valid_statuses]
        if statuses:
            stmt = stmt.where(TrendAlert.status.in_(statuses))

    alerts = (await db.execute(stmt)).scalars().all()
    return [_serialize_alert(a) for a in alerts]


# ── GET /api/trends/stats ────────────────────────────────────────────

@router.get("/stats")
async def trend_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Quick stats for the trend radar dashboard."""
    uid = current_user.id

    # Count by status
    counts: dict[str, int] = {}
    for s in ["detected", "generating", "ready", "published", "dismissed", "failed"]:
        cnt = (await db.execute(
            select(func.count())
            .select_from(TrendAlert)
            .where(TrendAlert.user_id == uid, TrendAlert.status == s)
        )).scalar() or 0
        counts[s] = cnt

    # Today's auto-publishes
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    auto_today = (await db.execute(
        select(func.count())
        .select_from(TrendAlert)
        .where(
            TrendAlert.user_id == uid,
            TrendAlert.auto_published == True,  # noqa: E712
            TrendAlert.published_at >= today_start,
        )
    )).scalar() or 0

    settings = await _get_or_create_settings(db, uid)

    return {
        "total_detected": counts.get("detected", 0),
        "total_generating": counts.get("generating", 0),
        "total_ready": counts.get("ready", 0),
        "total_published": counts.get("published", 0),
        "total_dismissed": counts.get("dismissed", 0),
        "total_failed": counts.get("failed", 0),
        "auto_published_today": auto_today,
        "autopilot_enabled": settings.autopilot_enabled,
    }


# ── POST /api/trends/scan ───────────────────────────────────────────

@router.post("/scan")
@limiter.limit("3/hour")
async def force_scan(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force an immediate trend scan for the current user."""
    from backend.services.trend_service import detect_trending_topics, save_trend_alerts

    # Get user preferences
    prefs = (await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )).scalar_one_or_none()

    if not prefs or not prefs.niches_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete onboarding and select your niches first.",
        )

    try:
        niches = json.loads(prefs.niches_json)
    except (json.JSONDecodeError, TypeError):
        niches = []

    if not niches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No niches configured. Go to Settings to add your niches.",
        )

    # Get API keys
    keys = (await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )).scalar_one_or_none()

    if not keys or not keys.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings → API Keys.",
        )

    openai_key = decrypt_or_raise(keys.openai_api_key, field="openai_api_key")

    # Get covered topics for dedup
    covered_stmt = (
        select(ContentMemory.title)
        .where(ContentMemory.user_id == current_user.id)
        .order_by(ContentMemory.created_at.desc())
        .limit(30)
    )
    covered = [t for t in (await db.execute(covered_stmt)).scalars().all() if t]

    # Get default channel
    channel = (await db.execute(
        select(Channel).where(
            Channel.user_id == current_user.id,
            Channel.is_default == True,  # noqa: E712
        )
    )).scalar_one_or_none()

    settings = await _get_or_create_settings(db, current_user.id)

    # Get SerpAPI key for live web trends
    from backend.config import get_settings as _get_app_settings
    serpapi_key = _get_app_settings().serpapi_api_key

    # Scan all niches
    all_alerts = []
    for niche in niches[:3]:
        try:
            topics = await asyncio.to_thread(
                detect_trending_topics,
                niche=niche,
                openai_api_key=openai_key,
                tone_style=prefs.tone_style or "confident, direct, no-fluff educator",
                target_audience=prefs.target_audience or "general audience",
                already_covered=covered,
                serpapi_key=serpapi_key,
            )

            alerts = await save_trend_alerts(
                user_id=current_user.id,
                channel_id=channel.id if channel else None,
                niche=niche,
                topics=topics,
                db_session=db,
                min_confidence=settings.min_confidence_threshold,
            )
            all_alerts.extend(alerts)
        except Exception as e:
            logger.exception("Manual trend scan failed for niche=%s", niche)

    # Stamp last_scanned_at so the background worker respects the cooldown
    settings.last_scanned_at = datetime.now(timezone.utc)
    settings.updated_at = settings.last_scanned_at

    await db.commit()

    return {
        "message": f"Scan complete! Found {len(all_alerts)} new trending topics.",
        "new_alerts": len(all_alerts),
        "alerts": [_serialize_alert(a) for a in all_alerts],
    }


# ── POST /api/trends/{id}/publish ────────────────────────────────────

@router.post("/{alert_id}/publish")
async def publish_trend(
    alert_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One-tap publish a ready trend video, or trigger generation for a detected trend."""
    alert = (await db.execute(
        select(TrendAlert).where(
            TrendAlert.id == alert_id,
            TrendAlert.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Trend alert not found.")

    if alert.status == "detected":
        # Trigger video generation first
        keys = (await db.execute(
            select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
        )).scalar_one_or_none()

        if not keys or not keys.openai_api_key or not keys.elevenlabs_api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please add your API keys in Settings before generating videos.",
            )

        # Check if user already has a video in-flight
        from backend.routers.videos import user_has_inflight_video
        if await user_has_inflight_video(current_user.id, db):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a video generating. Please wait for it to finish first.",
            )

        channel = None
        if alert.channel_id:
            channel = (await db.execute(
                select(Channel).where(Channel.id == alert.channel_id)
            )).scalar_one_or_none()

        from backend.workers.trend_radar_worker import _trigger_video_generation
        await _trigger_video_generation(db, alert, current_user, keys, channel)

        return {
            "message": "Video generation started! This takes 2-5 minutes.",
            "status": "generating",
            "video_record_id": alert.video_record_id,
        }

    if alert.status == "ready":
        # The video is already generated. If it hasn't been uploaded to YT yet,
        # we can trigger the upload. For now, mark as published.
        now = datetime.now(timezone.utc)
        alert.status = "published"
        alert.published_at = now
        alert.updated_at = now
        await db.commit()

        return {
            "message": "Trend published successfully! 🚀",
            "status": "published",
            "video_record_id": alert.video_record_id,
        }

    if alert.status == "generating":
        return {
            "message": "Video is still being generated. Check back in a moment.",
            "status": "generating",
        }

    if alert.status == "published":
        return {"message": "This trend has already been published.", "status": "published"}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Cannot publish trend with status '{alert.status}'.",
    )


# ── POST /api/trends/{id}/dismiss ────────────────────────────────────

@router.post("/{alert_id}/dismiss")
async def dismiss_trend(
    alert_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a trend alert (won't appear in the queue anymore)."""
    alert = (await db.execute(
        select(TrendAlert).where(
            TrendAlert.id == alert_id,
            TrendAlert.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Trend alert not found.")

    if alert.status in ("published",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot dismiss a published trend.",
        )

    now = datetime.now(timezone.utc)
    alert.status = "dismissed"
    alert.dismissed_at = now
    alert.updated_at = now
    await db.commit()

    return {"message": "Trend dismissed.", "status": "dismissed"}


# ── POST /api/trends/{id}/regenerate ─────────────────────────────────

@router.post("/{alert_id}/regenerate")
async def regenerate_trend(
    alert_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-generate a failed trend's video."""
    alert = (await db.execute(
        select(TrendAlert).where(
            TrendAlert.id == alert_id,
            TrendAlert.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Trend alert not found.")

    if alert.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed trends can be regenerated.",
        )

    # Reset to detected so it gets picked up again
    alert.status = "detected"
    alert.error_message = None
    alert.video_record_id = None
    alert.generation_started_at = None
    alert.updated_at = datetime.now(timezone.utc)

    # Immediately trigger generation
    keys = (await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )).scalar_one_or_none()

    if keys and keys.openai_api_key and keys.elevenlabs_api_key:
        # Check if user already has a video in-flight
        from backend.routers.videos import user_has_inflight_video
        if await user_has_inflight_video(current_user.id, db):
            await db.commit()
            return {
                "message": "You already have a video generating. This trend will be retried automatically once it finishes.",
                "status": "detected",
            }

        channel = None
        if alert.channel_id:
            channel = (await db.execute(
                select(Channel).where(Channel.id == alert.channel_id)
            )).scalar_one_or_none()

        from backend.workers.trend_radar_worker import _trigger_video_generation
        await _trigger_video_generation(db, alert, current_user, keys, channel)
    else:
        await db.commit()

    return {
        "message": "Regenerating video for this trend…",
        "status": alert.status,
    }


# ── GET /api/trends/settings ─────────────────────────────────────────

@router.get("/settings")
async def get_settings_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's Trend Radar settings."""
    settings = await _get_or_create_settings(db, current_user.id)
    await db.commit()

    return {
        "is_enabled": settings.is_enabled,
        "autopilot_enabled": settings.autopilot_enabled,
        "autopilot_min_confidence": settings.autopilot_min_confidence,
        "autopilot_daily_cap": settings.autopilot_daily_cap,
        "scan_interval_minutes": settings.scan_interval_minutes,
        "min_confidence_threshold": settings.min_confidence_threshold,
    }


# ── PUT /api/trends/settings ─────────────────────────────────────────

@router.put("/settings")
async def update_settings_endpoint(
    body: TrendSettingsUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update Trend Radar settings (autopilot toggle, thresholds, etc.)."""
    settings = await _get_or_create_settings(db, current_user.id)

    if body.is_enabled is not None:
        settings.is_enabled = body.is_enabled

        # ── When user disables Trend Radar, dismiss all pending alerts ──
        # This prevents stale "detected" alerts from being processed if
        # the user re-enables later.
        if not body.is_enabled:
            from sqlalchemy import update
            await db.execute(
                update(TrendAlert)
                .where(
                    TrendAlert.user_id == current_user.id,
                    TrendAlert.status.in_(["detected"]),
                )
                .values(
                    status="dismissed",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            logger.info(
                "Trend Radar disabled for user %s — dismissed pending detected alerts",
                current_user.email,
            )

    if body.autopilot_enabled is not None:
        settings.autopilot_enabled = body.autopilot_enabled
    if body.autopilot_min_confidence is not None:
        settings.autopilot_min_confidence = body.autopilot_min_confidence
    if body.autopilot_daily_cap is not None:
        settings.autopilot_daily_cap = body.autopilot_daily_cap
    if body.scan_interval_minutes is not None:
        settings.scan_interval_minutes = body.scan_interval_minutes
    if body.min_confidence_threshold is not None:
        settings.min_confidence_threshold = body.min_confidence_threshold

    settings.updated_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "Trend Radar settings updated for user %s: autopilot=%s cap=%d confidence=%d",
        current_user.email, settings.autopilot_enabled,
        settings.autopilot_daily_cap, settings.autopilot_min_confidence,
    )

    return {
        "message": "Settings updated.",
        "is_enabled": settings.is_enabled,
        "autopilot_enabled": settings.autopilot_enabled,
        "autopilot_min_confidence": settings.autopilot_min_confidence,
        "autopilot_daily_cap": settings.autopilot_daily_cap,
        "scan_interval_minutes": settings.scan_interval_minutes,
        "min_confidence_threshold": settings.min_confidence_threshold,
    }
