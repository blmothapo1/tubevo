# filepath: backend/analytics_worker.py
"""
Background analytics worker — YouTube metrics ingestion.

Runs as an asyncio task inside the FastAPI lifespan (alongside the
existing ``scheduler_worker``).  Every hour it scans for published
videos in the 24–72 hour eligibility window that haven't had their
48-hour metrics captured yet, fetches real data from YouTube, and
updates the ``content_performance`` table.

All failures are non-fatal: a failed fetch logs a warning and moves on.
The worker never impacts generation, rendering, or uploading.

Eligibility window:
    now - 72h  ≤  published_at  ≤  now - 24h
This ensures YouTube has had time to aggregate meaningful data (≥24h)
while still capturing the critical early-performance window (≤72h).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models import ContentPerformance, OAuthToken, VideoRecord

logger = logging.getLogger("tubevo.backend.analytics_worker")

# How often to check for eligible videos (seconds)
ANALYTICS_POLL_INTERVAL = 60 * 60  # 1 hour

# Eligibility window boundaries (hours after publish)
ELIGIBILITY_MIN_HOURS = 24
ELIGIBILITY_MAX_HOURS = 72

# Maximum videos to process per cycle (quota protection)
MAX_VIDEOS_PER_CYCLE = 25


async def analytics_loop() -> None:
    """Main analytics loop — runs forever, checking for eligible videos."""
    logger.info(
        "📊 Analytics worker started (poll every %ds, window %d–%dh)",
        ANALYTICS_POLL_INTERVAL,
        ELIGIBILITY_MIN_HOURS,
        ELIGIBILITY_MAX_HOURS,
    )

    # Initial delay — let the app fully start and other tasks settle
    await asyncio.sleep(30)

    while True:
        try:
            processed = await _process_eligible_videos()
            if processed > 0:
                logger.info("Analytics cycle complete: %d videos updated", processed)
        except Exception:
            logger.exception("Analytics worker iteration failed (non-fatal)")

        await asyncio.sleep(ANALYTICS_POLL_INTERVAL)


async def _process_eligible_videos() -> int:
    """Find and process all videos eligible for 48h metrics capture.

    Returns the number of videos successfully updated.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=ELIGIBILITY_MAX_HOURS)  # published >= 72h ago
    window_end = now - timedelta(hours=ELIGIBILITY_MIN_HOURS)    # published <= 24h ago

    processed = 0

    async with async_session_factory() as db:
        # Find videos that:
        # 1. Have a youtube_video_id (were uploaded to YouTube)
        # 2. Are in "posted" status
        # 3. Were published within the eligibility window
        # 4. Have a ContentPerformance row with metrics_fetched_at IS NULL
        #    (haven't had 48h metrics captured yet)

        # Subquery: video_record_ids that already have metrics
        from sqlalchemy import exists

        already_fetched = (
            select(ContentPerformance.video_record_id)
            .where(ContentPerformance.metrics_fetched_at != None)  # noqa: E711
            .correlate(VideoRecord)
        )

        stmt = (
            select(VideoRecord)
            .where(
                and_(
                    VideoRecord.youtube_video_id != None,  # noqa: E711
                    VideoRecord.status == "posted",
                    VideoRecord.published_at != None,  # noqa: E711
                    VideoRecord.published_at >= window_start,
                    VideoRecord.published_at <= window_end,
                    ~exists(
                        select(ContentPerformance.id).where(
                            and_(
                                ContentPerformance.video_record_id == VideoRecord.id,
                                ContentPerformance.metrics_fetched_at != None,  # noqa: E711
                            )
                        )
                    ),
                )
            )
            .order_by(VideoRecord.published_at.asc())
            .limit(MAX_VIDEOS_PER_CYCLE)
        )

        result = await db.execute(stmt)
        eligible_videos = result.scalars().all()

        if not eligible_videos:
            return 0

        logger.info(
            "Analytics: found %d eligible videos (window %s → %s)",
            len(eligible_videos),
            window_start.isoformat()[:19],
            window_end.isoformat()[:19],
        )

        # Group by user_id to batch token lookups
        user_ids = list({v.user_id for v in eligible_videos})

        # Pre-fetch OAuth tokens for all relevant users
        token_stmt = select(OAuthToken).where(
            and_(
                OAuthToken.user_id.in_(user_ids),
                OAuthToken.provider == "google",
            )
        )
        token_result = await db.execute(token_stmt)
        tokens_by_user: dict[str, OAuthToken] = {
            t.user_id: t for t in token_result.scalars().all()
        }

        for video in eligible_videos:
            try:
                success = await _fetch_and_update_single(
                    db=db,
                    video=video,
                    oauth_token=tokens_by_user.get(video.user_id),
                )
                if success:
                    processed += 1
            except Exception as exc:
                logger.warning(
                    "Analytics: failed to process video %s (%s): %s",
                    video.id, video.youtube_video_id, exc,
                )

        await db.commit()

    return processed


async def _fetch_and_update_single(
    *,
    db: AsyncSession,
    video: VideoRecord,
    oauth_token: OAuthToken | None,
) -> bool:
    """Fetch metrics for a single video and update its ContentPerformance row.

    Returns True if metrics were successfully fetched and saved.
    """
    if not oauth_token:
        logger.info(
            "Analytics: skipping %s — user %s has no OAuth token",
            video.youtube_video_id, video.user_id,
        )
        return False

    if not oauth_token.refresh_token:
        logger.info(
            "Analytics: skipping %s — no refresh token (can't refresh access)",
            video.youtube_video_id,
        )
        return False

    # Import settings for client_id / client_secret
    from backend.config import get_settings
    settings = get_settings()

    if not settings.google_client_id or not settings.google_client_secret:
        logger.warning("Analytics: Google OAuth not configured — skipping")
        return False

    if not video.youtube_video_id:
        return False  # safety — should never happen due to query filter

    # Fetch metrics in a thread to avoid blocking the async loop
    # (google API client is synchronous)
    from backend.youtube_analytics import fetch_video_metrics

    metrics = await asyncio.to_thread(
        fetch_video_metrics,
        youtube_video_id=video.youtube_video_id,
        channel_id=oauth_token.channel_id,
        access_token=oauth_token.access_token,
        refresh_token=oauth_token.refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        granted_scopes=oauth_token.scopes,
        published_at=video.published_at,
    )

    if not metrics:
        logger.info(
            "Analytics: no metrics returned for %s — will retry next cycle",
            video.youtube_video_id,
        )
        return False

    # Find the ContentPerformance row for this video
    cp_stmt = select(ContentPerformance).where(
        ContentPerformance.video_record_id == video.id,
    )
    cp_result = await db.execute(cp_stmt)
    cp_row = cp_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if cp_row:
        # Update existing row
        if "views_48h" in metrics:
            cp_row.views_48h = metrics["views_48h"]
        if "likes_48h" in metrics:
            cp_row.likes_48h = metrics["likes_48h"]
        if "comments_48h" in metrics:
            cp_row.comments_48h = metrics["comments_48h"]
        if "ctr_pct" in metrics:
            cp_row.ctr_pct = metrics["ctr_pct"]
        if "avg_view_duration_pct" in metrics:
            cp_row.avg_view_duration_pct = metrics["avg_view_duration_pct"]
        if "engagement_score" in metrics:
            cp_row.engagement_score = metrics["engagement_score"]
        cp_row.metrics_fetched_at = now
        cp_row.updated_at = now

        logger.info(
            "Analytics: updated ContentPerformance for %s — views=%s likes=%s ctr=%s retention=%s score=%s",
            video.youtube_video_id,
            cp_row.views_48h,
            cp_row.likes_48h,
            cp_row.ctr_pct,
            cp_row.avg_view_duration_pct,
            cp_row.engagement_score,
        )
    else:
        # No ContentPerformance row yet (edge case: upload succeeded but CP save failed)
        # Create one with metrics
        cp_entry = ContentPerformance(
            user_id=video.user_id,
            video_record_id=video.id,
            title_variant_used=video.title,
            views_48h=metrics.get("views_48h", 0),
            likes_48h=metrics.get("likes_48h", 0),
            comments_48h=metrics.get("comments_48h", 0),
            ctr_pct=metrics.get("ctr_pct"),
            avg_view_duration_pct=metrics.get("avg_view_duration_pct"),
            engagement_score=metrics.get("engagement_score", 0),
            metrics_fetched_at=now,
        )
        db.add(cp_entry)

        logger.info(
            "Analytics: created ContentPerformance for %s (was missing) — score=%s",
            video.youtube_video_id, cp_entry.engagement_score,
        )

    # Update the OAuth token's access_token if it was refreshed
    # (the credentials object may have a new token after refresh)
    # This is handled transparently by google-auth — no action needed here.

    return True


async def manual_refresh_metrics(user_id: str) -> dict:
    """Manually trigger metrics refresh for a specific user's eligible videos.

    Used by the admin/manual trigger endpoint.
    Returns a summary dict.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=ELIGIBILITY_MAX_HOURS)
    window_end = now - timedelta(hours=ELIGIBILITY_MIN_HOURS)

    async with async_session_factory() as db:
        stmt = (
            select(VideoRecord)
            .where(
                and_(
                    VideoRecord.user_id == user_id,
                    VideoRecord.youtube_video_id != None,  # noqa: E711
                    VideoRecord.status == "posted",
                    VideoRecord.published_at != None,  # noqa: E711
                    VideoRecord.published_at >= window_start,
                    VideoRecord.published_at <= window_end,
                )
            )
            .order_by(VideoRecord.published_at.asc())
            .limit(MAX_VIDEOS_PER_CYCLE)
        )

        result = await db.execute(stmt)
        eligible = result.scalars().all()

        if not eligible:
            return {"eligible": 0, "updated": 0, "message": "No videos in the 24-72h window"}

        # Fetch OAuth token
        token_stmt = select(OAuthToken).where(
            and_(
                OAuthToken.user_id == user_id,
                OAuthToken.provider == "google",
            )
        )
        token = (await db.execute(token_stmt)).scalar_one_or_none()

        updated = 0
        errors = []
        for video in eligible:
            try:
                success = await _fetch_and_update_single(
                    db=db,
                    video=video,
                    oauth_token=token,
                )
                if success:
                    updated += 1
            except Exception as exc:
                errors.append(f"{video.youtube_video_id}: {exc}")

        await db.commit()

    return {
        "eligible": len(eligible),
        "updated": updated,
        "errors": errors if errors else None,
        "window": f"{window_start.isoformat()[:19]}Z → {window_end.isoformat()[:19]}Z",
    }
