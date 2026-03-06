# filepath: backend/workers/trend_radar_worker.py
"""
Trend Radar background worker.

Periodically scans each user's niches for trending topics, then auto-generates
videos for high-confidence trends. Videos land in a "Ready to Fire" queue
where users can one-tap publish, or are auto-published if autopilot is on.

This is the brain of the Trend-to-Video pipeline:
  1. Detect trends via GPT (trend_service.detect_trending_topics)
  2. For high-confidence trends, trigger the video pipeline
  3. When video is ready, mark alert as "ready" (or auto-publish if autopilot)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.database import async_session_factory
from backend.encryption import decrypt, decrypt_or_raise
from backend.feature_flags import FF_TREND_RADAR, is_globally_enabled
from backend.models import (
    Channel, ContentMemory, OAuthToken, TrendAlert, TrendRadarSettings,
    User, UserApiKeys, UserPreferences, VideoRecord,
)
from backend.utils import PLAN_MONTHLY_LIMITS

logger = logging.getLogger("tubevo.worker.trend_radar")

# Default scan interval (6 hours) — overridden per-user via TrendRadarSettings
_DEFAULT_INTERVAL_SECS = 60 * 60 * 6
# Worker poll interval (check every 5 minutes if any user is due for a scan)
_POLL_INTERVAL = 5 * 60
# Max trends to auto-generate per user per scan cycle
_MAX_AUTO_GENERATE_PER_CYCLE = 1
# Min confidence to auto-trigger video generation
_AUTO_GENERATE_MIN_CONFIDENCE = 65
# Max pending (detected + generating) alerts per user before we stop scanning
_MAX_PENDING_ALERTS = 10


async def _get_or_create_settings(db, user_id: str) -> TrendRadarSettings:
    """Get user's trend radar settings, creating defaults if needed."""
    from backend.models import _new_uuid, _utcnow

    result = await db.execute(
        select(TrendRadarSettings).where(TrendRadarSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = TrendRadarSettings(
            id=_new_uuid(),
            user_id=user_id,
            is_enabled=True,
            created_at=_utcnow(),
        )
        db.add(settings)
        await db.flush()
    return settings


async def _get_user_covered_topics(db, user_id: str) -> list[str]:
    """Get list of topics this user has already covered (for dedup)."""
    stmt = (
        select(ContentMemory.title)
        .where(ContentMemory.user_id == user_id)
        .order_by(ContentMemory.created_at.desc())
        .limit(30)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [t for t in rows if t]


async def _check_plan_quota(db, user: User) -> bool:
    """Return True if user still has video quota remaining this month."""
    now = datetime.now(timezone.utc)
    plan = user.plan or "free"
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == user.id,
            VideoRecord.created_at >= month_start,
            VideoRecord.status.notin_(["failed"]),
        )
    )
    monthly_count = (await db.execute(count_stmt)).scalar() or 0
    return monthly_count < limit


async def _count_todays_auto_publishes(db, user_id: str) -> int:
    """Count how many auto-publishes happened today for this user."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count())
        .select_from(TrendAlert)
        .where(
            TrendAlert.user_id == user_id,
            TrendAlert.auto_published == True,  # noqa: E712
            TrendAlert.published_at >= today_start,
        )
    )
    return (await db.execute(stmt)).scalar() or 0


async def _trigger_video_generation(
    db,
    alert: TrendAlert,
    user: User,
    user_keys: UserApiKeys,
    channel: Channel | None,
) -> None:
    """Trigger the video pipeline for a trend alert.

    Creates a VideoRecord, updates the alert status to 'generating',
    and fires off the pipeline as an asyncio task.
    """
    from backend.models import _utcnow
    from backend.routers.videos import _run_pipeline_background

    now = _utcnow()

    # Decrypt API keys
    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key")
    elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key")
    pexels_key = decrypt(user_keys.pexels_api_key) if user_keys.pexels_api_key else ""

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "",
        "pexels_api_key": pexels_key or "",
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop"),
        "burn_captions": getattr(user_keys, "burn_captions", True),
        "speech_speed": getattr(user_keys, "speech_speed", None),
    }

    # Get YouTube tokens
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    yt_access_token = decrypt(oauth_token.access_token) if oauth_token and oauth_token.access_token else None
    yt_refresh_token = decrypt(oauth_token.refresh_token) if oauth_token and oauth_token.refresh_token else None

    # Create video record
    record = VideoRecord(
        user_id=user.id,
        channel_id=alert.channel_id,
        topic=alert.trend_topic,
        title=alert.trend_topic,
        status="generating",
    )
    db.add(record)
    await db.flush()

    # Link alert to video record
    alert.video_record_id = record.id
    alert.status = "generating"
    alert.generation_started_at = now
    alert.updated_at = now

    await db.commit()

    logger.info(
        "🚀 Trend Radar: triggering pipeline for alert=%s topic='%s' user=%s",
        alert.id, alert.trend_topic[:60], user.email,
    )

    # Fire-and-forget the pipeline
    asyncio.create_task(
        _run_pipeline_background(
            record_id=record.id,
            topic=alert.trend_topic,
            user_id=user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )


async def _scan_user_trends(db, user: User, channel: Channel | None) -> int:
    """Scan for trending topics for a single user. Returns count of new alerts."""
    from backend.services.trend_service import detect_trending_topics, save_trend_alerts

    # ── Guard: don't flood the queue — if user already has ≥10 pending alerts, skip scan
    pending_count_stmt = (
        select(func.count())
        .select_from(TrendAlert)
        .where(
            TrendAlert.user_id == user.id,
            TrendAlert.status.in_(["detected", "generating"]),
        )
    )
    pending_count = (await db.execute(pending_count_stmt)).scalar() or 0
    if pending_count >= _MAX_PENDING_ALERTS:
        logger.info(
            "Trend Radar: user %s already has %d pending alerts — skipping scan",
            user.email, pending_count,
        )
        return 0

    # Get user preferences
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    if not prefs or not prefs.niches_json:
        return 0

    try:
        niches = json.loads(prefs.niches_json)
    except (json.JSONDecodeError, TypeError):
        return 0

    if not niches:
        return 0

    # Get API keys
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    if not user_keys or not user_keys.openai_api_key:
        return 0

    openai_key = decrypt(user_keys.openai_api_key)
    if not openai_key:
        return 0

    # Get settings
    settings = await _get_or_create_settings(db, user.id)
    if not settings.is_enabled:
        return 0

    tone_style = prefs.tone_style or "confident, direct, no-fluff educator"
    target_audience = prefs.target_audience or "general audience"
    covered = await _get_user_covered_topics(db, user.id)

    # Get SerpAPI key for live web trends
    from backend.config import get_settings
    serpapi_key = get_settings().serpapi_api_key

    total_created = 0

    # Scan each niche (max 3)
    for niche in niches[:3]:
        try:
            topics = await asyncio.to_thread(
                detect_trending_topics,
                niche=niche,
                openai_api_key=openai_key,
                tone_style=tone_style,
                target_audience=target_audience,
                already_covered=covered,
                serpapi_key=serpapi_key,
            )

            alerts = await save_trend_alerts(
                user_id=user.id,
                channel_id=channel.id if channel else None,
                niche=niche,
                topics=topics,
                db_session=db,
                min_confidence=settings.min_confidence_threshold,
            )
            total_created += len(alerts)

            logger.info(
                "Trend Radar: detected %d trends for user=%s niche=%s (%d new alerts)",
                len(topics), user.email, niche, len(alerts),
            )
        except Exception:
            logger.exception(
                "Trend Radar: scan failed for user=%s niche=%s",
                user.email, niche,
            )

    return total_created


async def _process_detected_alerts(db) -> int:
    """Process 'detected' alerts: auto-generate videos for high-confidence ones.

    Returns count of alerts moved to 'generating'.
    """
    # Find all detected alerts with high enough confidence
    stmt = (
        select(TrendAlert)
        .where(
            TrendAlert.status == "detected",
            TrendAlert.confidence_score >= _AUTO_GENERATE_MIN_CONFIDENCE,
        )
        .order_by(TrendAlert.confidence_score.desc())
        .limit(10)
    )
    alerts = (await db.execute(stmt)).scalars().all()

    if not alerts:
        return 0

    generated = 0
    # Group by user to enforce per-user limits
    user_counts: dict[str, int] = {}

    for alert in alerts:
        uid = alert.user_id
        if user_counts.get(uid, 0) >= _MAX_AUTO_GENERATE_PER_CYCLE:
            continue

        # Get user
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if not user or not user.is_active:
            continue

        # Check quota
        if not await _check_plan_quota(db, user):
            logger.info("Trend Radar: user %s at quota limit, skipping generation", user.email)
            continue

        # Check if user already has a video in-flight — don't pile up
        from backend.routers.videos import user_has_inflight_video
        if await user_has_inflight_video(uid, db):
            logger.info("Trend Radar: user %s already has a video generating — skipping", user.email)
            continue

        # Get API keys
        keys = (await db.execute(
            select(UserApiKeys).where(UserApiKeys.user_id == uid)
        )).scalar_one_or_none()
        if not keys or not keys.openai_api_key or not keys.elevenlabs_api_key:
            continue

        # Get channel
        channel = None
        if alert.channel_id:
            channel = (await db.execute(
                select(Channel).where(Channel.id == alert.channel_id)
            )).scalar_one_or_none()

        try:
            await _trigger_video_generation(db, alert, user, keys, channel)
            user_counts[uid] = user_counts.get(uid, 0) + 1
            generated += 1
        except Exception:
            logger.exception(
                "Trend Radar: failed to trigger generation for alert=%s",
                alert.id,
            )
            alert.status = "failed"
            alert.error_message = "Failed to trigger video generation"
            alert.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return generated


async def _check_ready_alerts(db) -> int:
    """Check 'generating' alerts whose videos are now complete.

    Moves them to 'ready' (or auto-publishes if autopilot is on).
    Also fails alerts stuck in 'generating' for over 30 minutes.
    Returns count of alerts moved to 'ready'.
    """
    stmt = (
        select(TrendAlert)
        .where(TrendAlert.status == "generating")
    )
    alerts = (await db.execute(stmt)).scalars().all()

    if not alerts:
        return 0

    ready_count = 0
    changed = False
    now = datetime.now(timezone.utc)

    for alert in alerts:
        # ── Fail alerts stuck generating for >30 min ─────────────
        if alert.generation_started_at:
            stuck_seconds = (now - alert.generation_started_at).total_seconds()
            if stuck_seconds > 1800:  # 30 minutes
                alert.status = "failed"
                alert.error_message = "Video generation timed out (>30 min)"
                alert.updated_at = now
                changed = True
                logger.warning(
                    "Trend Radar: timed out stuck alert=%s (%.0fs)",
                    alert.id, stuck_seconds,
                )
                continue

        if not alert.video_record_id:
            continue

        # Check video status
        video = (await db.execute(
            select(VideoRecord).where(VideoRecord.id == alert.video_record_id)
        )).scalar_one_or_none()

        if not video:
            continue

        if video.status == "completed" or video.status == "posted":
            alert.status = "ready"
            alert.ready_at = now
            alert.generated_title = video.title
            alert.script_preview = (video.script_text or "")[:500]
            alert.thumbnail_path = video.thumbnail_path
            alert.updated_at = now
            ready_count += 1
            changed = True

            # Check if autopilot should auto-publish
            settings = await _get_or_create_settings(db, alert.user_id)
            if settings.autopilot_enabled and video.status == "completed":
                # Check confidence threshold + daily cap
                if alert.confidence_score >= settings.autopilot_min_confidence:
                    today_count = await _count_todays_auto_publishes(db, alert.user_id)
                    if today_count < settings.autopilot_daily_cap:
                        alert.status = "published"
                        alert.published_at = now
                        alert.auto_published = True
                        alert.updated_at = now
                        logger.info(
                            "🤖 Autopilot: auto-published trend alert=%s topic='%s'",
                            alert.id, alert.trend_topic[:60],
                        )

            # If video was already posted by pipeline (had YT tokens), mark published
            if video.status == "posted":
                alert.status = "published"
                alert.published_at = now
                alert.updated_at = now

        elif video.status == "failed":
            alert.status = "failed"
            alert.error_message = video.error_message or "Video generation failed"
            alert.updated_at = now
            changed = True

    if changed:
        await db.commit()

    return ready_count


async def _run_trend_cycle() -> None:
    """Run one complete trend radar cycle across all users.

    Respects each user's ``scan_interval_minutes`` so we don't hammer GPT
    every 5 minutes and flood the queue with "detected" alerts.
    """
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        # 1. Scan for new trends — only for users whose cooldown has elapsed
        users_result = await db.execute(
            select(User).where(User.is_active == True)  # noqa: E712
        )
        users = users_result.scalars().all()

        total_alerts = 0
        for user in users:
            try:
                settings = await _get_or_create_settings(db, user.id)
                if not settings.is_enabled:
                    continue

                # ── Enforce scan_interval_minutes cooldown ───────────
                interval_secs = (settings.scan_interval_minutes or 360) * 60
                if settings.last_scanned_at:
                    elapsed = (now - settings.last_scanned_at).total_seconds()
                    if elapsed < interval_secs:
                        continue  # Not due yet

                # Get user's default channel
                channel_result = await db.execute(
                    select(Channel).where(
                        Channel.user_id == user.id,
                        Channel.is_default == True,  # noqa: E712
                    )
                )
                channel = channel_result.scalar_one_or_none()

                new_alerts = await _scan_user_trends(db, user, channel)
                total_alerts += new_alerts

                # Stamp the scan time so we don't re-scan too soon
                settings.last_scanned_at = now
                settings.updated_at = now
            except Exception:
                logger.exception("Trend Radar: scan cycle failed for user=%s", user.email)

        if total_alerts:
            await db.commit()
            logger.info("📡 Trend Radar: detected %d new trends across %d users", total_alerts, len(users))
        else:
            # Still need to commit `last_scanned_at` updates
            await db.commit()

    # 2. Process detected alerts → trigger video generation
    async with async_session_factory() as db:
        generated = await _process_detected_alerts(db)
        if generated:
            logger.info("🎬 Trend Radar: triggered %d video generations", generated)

    # 3. Check generating alerts → move to ready
    async with async_session_factory() as db:
        ready = await _check_ready_alerts(db)
        if ready:
            logger.info("✅ Trend Radar: %d videos now ready to fire", ready)


async def trend_radar_loop() -> None:
    """Long-running loop: run trend radar scans periodically."""
    logger.info("📡 Trend Radar worker started (poll every %ds)", _POLL_INTERVAL)

    while True:
        try:
            if not is_globally_enabled(FF_TREND_RADAR):
                await asyncio.sleep(_POLL_INTERVAL)
                continue

            await _run_trend_cycle()
            await asyncio.sleep(_POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Trend Radar worker shutting down")
            break
        except Exception:
            logger.exception("Trend Radar worker error (will retry in 60s)")
            await asyncio.sleep(60)
