# filepath: backend/services/competitor_service.py
"""
Competitor Monitoring service (Feature 5: Spy Mode).

Manages the lifecycle of competitor channel tracking:
  - Add / remove competitor channels (linked to user's channel)
  - Store daily snapshots of competitor metrics
  - Retrieve snapshot history for trend analysis
  - Compute summary comparisons

Each user channel can track up to ``MAX_COMPETITORS`` competitor YouTube
channels.  Snapshots are stored once per day per competitor and include
subscriber count, total views, video count, and derived metrics.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    CompetitorChannel,
    CompetitorSnapshot,
    _new_uuid,
    _utcnow,
)

logger = logging.getLogger("tubevo.backend.competitor_service")

# Limits
MAX_COMPETITORS = 10


# ── Add competitor ───────────────────────────────────────────────────

async def add_competitor(
    *,
    channel_id: str,
    youtube_channel_id: str,
    name: str,
    subscriber_count: int | None = None,
    db: AsyncSession,
) -> CompetitorChannel:
    """Add a competitor channel to track.

    Raises
    ------
    ValueError
        If the competitor is already tracked or the limit is reached.
    """
    youtube_channel_id = youtube_channel_id.strip()
    name = name.strip()

    if not youtube_channel_id:
        raise ValueError("youtube_channel_id is required")
    if not name:
        raise ValueError("name is required")

    # Check limit
    count_result = await db.execute(
        select(func.count()).select_from(CompetitorChannel).where(
            CompetitorChannel.channel_id == channel_id,
            CompetitorChannel.is_active == True,  # noqa: E712
        )
    )
    current_count = count_result.scalar() or 0
    if current_count >= MAX_COMPETITORS:
        raise ValueError(
            f"Maximum {MAX_COMPETITORS} competitors per channel. "
            f"Remove one before adding another."
        )

    # Check duplicate
    dup_result = await db.execute(
        select(CompetitorChannel).where(
            CompetitorChannel.channel_id == channel_id,
            CompetitorChannel.youtube_channel_id == youtube_channel_id,
        )
    )
    existing = dup_result.scalar_one_or_none()
    if existing:
        if existing.is_active:
            raise ValueError(
                f"Already tracking YouTube channel {youtube_channel_id}"
            )
        # Re-activate previously removed competitor
        existing.is_active = True
        existing.name = name
        if subscriber_count is not None:
            existing.subscriber_count = subscriber_count
        await db.flush()
        return existing

    competitor = CompetitorChannel(
        id=_new_uuid(),
        channel_id=channel_id,
        youtube_channel_id=youtube_channel_id,
        name=name,
        subscriber_count=subscriber_count,
        is_active=True,
        created_at=_utcnow(),
    )
    db.add(competitor)
    await db.flush()
    return competitor


# ── Remove competitor ────────────────────────────────────────────────

async def remove_competitor(
    *,
    competitor_id: str,
    channel_id: str,
    db: AsyncSession,
) -> CompetitorChannel:
    """Soft-remove a competitor (set is_active=False).

    Raises
    ------
    ValueError
        If the competitor is not found or doesn't belong to the channel.
    """
    result = await db.execute(
        select(CompetitorChannel).where(
            CompetitorChannel.id == competitor_id,
            CompetitorChannel.channel_id == channel_id,
        )
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise ValueError("Competitor not found")

    if not competitor.is_active:
        raise ValueError("Competitor is already removed")

    competitor.is_active = False
    await db.flush()
    return competitor


# ── List competitors ─────────────────────────────────────────────────

async def list_competitors(
    *,
    channel_id: str,
    include_inactive: bool = False,
    db: AsyncSession,
) -> list[CompetitorChannel]:
    """Return all tracked competitors for a channel."""
    query = (
        select(CompetitorChannel)
        .where(CompetitorChannel.channel_id == channel_id)
        .order_by(CompetitorChannel.created_at.desc())
    )
    if not include_inactive:
        query = query.where(CompetitorChannel.is_active == True)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


# ── Get single competitor ────────────────────────────────────────────

async def get_competitor(
    *,
    competitor_id: str,
    channel_id: str,
    db: AsyncSession,
) -> CompetitorChannel | None:
    """Return a single competitor, or None."""
    result = await db.execute(
        select(CompetitorChannel).where(
            CompetitorChannel.id == competitor_id,
            CompetitorChannel.channel_id == channel_id,
        )
    )
    return result.scalar_one_or_none()


# ── Record snapshot ──────────────────────────────────────────────────

async def record_snapshot(
    *,
    competitor_id: str,
    snapshot_date: str,
    subscriber_count: int = 0,
    total_views: int = 0,
    video_count: int = 0,
    avg_views_per_video: int = 0,
    recent_videos: list[dict] | None = None,
    top_tags: list[str] | None = None,
    db: AsyncSession,
) -> CompetitorSnapshot:
    """Store a daily snapshot for a competitor.

    Uses upsert semantics — if a snapshot for this date already exists,
    it is updated in place.
    """
    # Check for existing snapshot on this date
    existing_result = await db.execute(
        select(CompetitorSnapshot).where(
            CompetitorSnapshot.competitor_id == competitor_id,
            CompetitorSnapshot.snapshot_date == snapshot_date,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.subscriber_count = subscriber_count
        existing.total_views = total_views
        existing.video_count = video_count
        existing.avg_views_per_video = avg_views_per_video
        existing.recent_videos_json = (
            json.dumps(recent_videos) if recent_videos else None
        )
        existing.top_tags_json = json.dumps(top_tags) if top_tags else None
        await db.flush()
        return existing

    snapshot = CompetitorSnapshot(
        id=_new_uuid(),
        competitor_id=competitor_id,
        snapshot_date=snapshot_date,
        subscriber_count=subscriber_count,
        total_views=total_views,
        video_count=video_count,
        avg_views_per_video=avg_views_per_video,
        recent_videos_json=(
            json.dumps(recent_videos) if recent_videos else None
        ),
        top_tags_json=json.dumps(top_tags) if top_tags else None,
        created_at=_utcnow(),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


# ── List snapshots ───────────────────────────────────────────────────

async def list_snapshots(
    *,
    competitor_id: str,
    limit: int = 30,
    db: AsyncSession,
) -> list[CompetitorSnapshot]:
    """Return recent snapshots for a competitor, newest first."""
    result = await db.execute(
        select(CompetitorSnapshot)
        .where(CompetitorSnapshot.competitor_id == competitor_id)
        .order_by(CompetitorSnapshot.snapshot_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ── Snapshot summary / trend ─────────────────────────────────────────

async def compute_growth_summary(
    *,
    competitor_id: str,
    db: AsyncSession,
) -> dict:
    """Compute a simple growth summary from the two most recent snapshots.

    Returns a dict with subscriber_change, view_change, video_change,
    and the two snapshot dates compared.
    """
    result = await db.execute(
        select(CompetitorSnapshot)
        .where(CompetitorSnapshot.competitor_id == competitor_id)
        .order_by(CompetitorSnapshot.snapshot_date.desc())
        .limit(2)
    )
    snapshots = list(result.scalars().all())

    if len(snapshots) < 2:
        return {
            "has_data": False,
            "subscriber_change": 0,
            "view_change": 0,
            "video_change": 0,
            "period_start": None,
            "period_end": None,
        }

    newest, oldest = snapshots[0], snapshots[1]
    return {
        "has_data": True,
        "subscriber_change": newest.subscriber_count - oldest.subscriber_count,
        "view_change": newest.total_views - oldest.total_views,
        "video_change": newest.video_count - oldest.video_count,
        "period_start": oldest.snapshot_date,
        "period_end": newest.snapshot_date,
    }
