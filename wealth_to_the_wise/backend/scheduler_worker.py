# filepath: backend/scheduler_worker.py
"""
Background scheduler worker.

Runs as an asyncio task inside the FastAPI lifespan.
Every 5 minutes it checks for active PostingSchedules whose
``next_run_at`` is in the past and triggers video generation
for the next topic in the queue.

This is a simple polling-based scheduler suitable for Railway's
single-container model.  For higher scale, swap this out for
Celery Beat or a cron-based job trigger.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.encryption import decrypt, decrypt_or_raise
from backend.models import OAuthToken, PostingSchedule, User, UserApiKeys, VideoRecord
from backend.routers.schedules import FREQUENCY_DELTAS
from backend.routers.videos import _run_pipeline_background
from backend.utils import PLAN_MONTHLY_LIMITS

logger = logging.getLogger("tubevo.backend.scheduler_worker")

# How often to check for due schedules (seconds)
POLL_INTERVAL = 5 * 60  # 5 minutes


async def scheduler_loop() -> None:
    """Main scheduler loop — runs forever, checking for due schedules."""
    logger.info("🕐 Scheduler worker started (poll every %ds)", POLL_INTERVAL)

    while True:
        try:
            await _process_due_schedules()
        except Exception:
            logger.exception("Scheduler worker iteration failed")

        await asyncio.sleep(POLL_INTERVAL)


async def _process_due_schedules() -> None:
    """Find and process all schedules that are due."""
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        result = await db.execute(
            select(PostingSchedule).where(
                PostingSchedule.is_active == True,  # noqa: E712
                PostingSchedule.next_run_at != None,  # noqa: E711
                PostingSchedule.next_run_at <= now,
            )
        )
        due_schedules = result.scalars().all()

        if not due_schedules:
            return

        logger.info("Scheduler: %d schedule(s) due for processing", len(due_schedules))

        for schedule in due_schedules:
            try:
                await _process_single_schedule(schedule, db)
            except Exception:
                logger.exception(
                    "Scheduler: failed to process schedule %s for user %s",
                    schedule.id, schedule.user_id,
                )
                # Mark next_run_at to avoid infinite retry loop
                delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
                schedule.next_run_at = now + delta
                schedule.updated_at = now

        await db.commit()


async def _process_single_schedule(schedule: PostingSchedule, db) -> None:
    """Process a single due schedule: pick the next topic and trigger generation."""
    now = datetime.now(timezone.utc)

    # Parse topics
    try:
        topics = json.loads(schedule.topics_json) if schedule.topics_json else []
    except (json.JSONDecodeError, TypeError):
        topics = []

    if not topics:
        logger.warning("Schedule %s has no topics — pausing.", schedule.id)
        schedule.is_active = False
        schedule.next_run_at = None
        schedule.updated_at = now
        return

    # Get the user
    user_result = await db.execute(
        select(User).where(User.id == schedule.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        logger.warning("Schedule %s: user not found or inactive — pausing.", schedule.id)
        schedule.is_active = False
        schedule.next_run_at = None
        schedule.updated_at = now
        return

    # Check plan limit
    plan = user.plan or "free"
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from sqlalchemy import func
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

    if monthly_count >= limit:
        logger.info(
            "Schedule %s: user %s hit monthly limit (%d/%d) — skipping, will retry next cycle.",
            schedule.id, user.email, monthly_count, limit,
        )
        # Push next_run_at forward to avoid hammering
        delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
        schedule.next_run_at = now + delta
        schedule.updated_at = now
        return

    # ── Per-user in-flight guard ─────────────────────────────────────
    # Skip if user already has a video generating — don't pile up jobs.
    # The schedule will simply fire again on the next poll cycle.
    from backend.routers.videos import user_has_inflight_video, is_circuit_broken
    if await user_has_inflight_video(user.id, db):
        logger.info(
            "Schedule %s: user %s already has a video generating — deferring to next cycle.",
            schedule.id, user.email,
        )
        # Don't advance next_run_at — retry on next poll (5 min)
        return

    # ── Circuit breaker: stop auto-generating if last N all failed ───
    if await is_circuit_broken(user.id, db):
        logger.warning(
            "Schedule %s: user %s circuit breaker tripped — last videos all failed. "
            "Pausing auto-generation to save API credits. User must generate manually to reset.",
            schedule.id, user.email,
        )
        delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
        schedule.next_run_at = now + delta
        schedule.updated_at = now
        return

    # Get user API keys
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
    pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""

    if not openai_key or not elevenlabs_key:
        logger.warning(
            "Schedule %s: user %s missing API keys — skipping.",
            schedule.id, user.email,
        )
        delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
        schedule.next_run_at = now + delta
        schedule.updated_at = now
        return

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        # Video production preferences (match generate_video / regenerate)
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
    }

    # Get YouTube tokens
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token") if oauth_token else None
    yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token") if oauth_token else None

    # Pick the topic
    idx = schedule.topic_index % len(topics)
    topic = topics[idx]

    # Create a video record
    record = VideoRecord(
        user_id=user.id,
        topic=topic,
        title=topic,
        status="generating",
    )
    db.add(record)
    await db.flush()
    record_id = record.id

    # Update schedule state
    schedule.topic_index = (idx + 1) % len(topics)
    schedule.last_run_at = now
    schedule.total_runs += 1

    # Compute next run
    delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
    next_run = now + delta
    schedule.next_run_at = next_run
    schedule.updated_at = now

    logger.info(
        "Scheduler: triggering video for schedule %s, user %s, topic='%s' (%d/%d). Next run: %s",
        schedule.id, user.email, topic, idx + 1, len(topics),
        next_run.isoformat(),
    )

    # Fire and forget the pipeline
    asyncio.create_task(
        _run_pipeline_background(
            record_id=record_id,
            topic=topic,
            user_id=user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )
