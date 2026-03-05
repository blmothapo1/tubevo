# filepath: backend/services/revenue_service.py
"""
Revenue Attribution service (Feature 3).

Provides:
  - Recording individual revenue events (adsense, affiliate, stripe, manual)
  - Aggregating daily revenue summaries per channel
  - Computing summary statistics (total, by source, top videos)

Revenue sources
---------------
- ``adsense``   — YouTube AdSense earnings (estimated, pulled via Analytics API)
- ``affiliate`` — Affiliate link revenue (manually recorded or via webhook)
- ``stripe``    — Stripe subscription / one-time payments
- ``manual``    — Manual entries from the user

All amounts are stored in **cents** (integer) to avoid floating-point issues.
Currency is always USD for v1.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    RevenueEvent,
    RevenueDailyAgg,
    VideoRecord,
    _new_uuid,
    _utcnow,
)

logger = logging.getLogger("tubevo.backend.revenue_service")

# Valid revenue sources
VALID_SOURCES = {"adsense", "affiliate", "stripe", "manual"}


# ── Record a single revenue event ───────────────────────────────────

async def record_revenue_event(
    *,
    channel_id: str,
    source: str,
    amount_cents: int,
    event_date: str,
    video_record_id: str | None = None,
    external_id: str | None = None,
    metadata: dict | None = None,
    db: AsyncSession,
) -> RevenueEvent:
    """Create a single revenue event row.

    Deduplicates on (source, external_id) — if external_id is provided
    and already exists, raises ValueError.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid revenue source: {source}. Must be one of {VALID_SOURCES}")

    if amount_cents < 0:
        raise ValueError("amount_cents must be non-negative")

    # Dedup check
    if external_id:
        existing = await db.execute(
            select(RevenueEvent).where(
                RevenueEvent.source == source,
                RevenueEvent.external_id == external_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Duplicate revenue event: source={source} external_id={external_id}")

    event = RevenueEvent(
        id=_new_uuid(),
        channel_id=channel_id,
        video_record_id=video_record_id,
        source=source,
        amount_cents=amount_cents,
        currency="USD",
        event_date=event_date,
        external_id=external_id,
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=_utcnow(),
    )
    db.add(event)
    await db.flush()
    return event


# ── Aggregate daily revenue ──────────────────────────────────────────

async def aggregate_daily_revenue(
    *,
    channel_id: str,
    agg_date: str,
    db: AsyncSession,
) -> RevenueDailyAgg:
    """(Re-)compute the daily aggregate for a channel + date.

    Sums all RevenueEvent rows for that channel+date, grouped by source.
    Upserts into RevenueDailyAgg.
    """
    # Query totals by source for this channel + date
    result = await db.execute(
        select(
            RevenueEvent.source,
            func.sum(RevenueEvent.amount_cents).label("total"),
            func.count(RevenueEvent.id).label("event_count"),
        )
        .where(
            RevenueEvent.channel_id == channel_id,
            RevenueEvent.event_date == agg_date,
        )
        .group_by(RevenueEvent.source)
    )
    rows = result.all()

    adsense_cents = 0
    affiliate_cents = 0
    stripe_cents = 0
    total_cents = 0
    video_count = 0

    for row in rows:
        source, total, count = row[0], int(row[1] or 0), int(row[2] or 0)
        total_cents += total
        if source == "adsense":
            adsense_cents = total
        elif source == "affiliate":
            affiliate_cents = total
        elif source == "stripe":
            stripe_cents = total
        # manual goes into total but not a specific bucket
        video_count += count

    # Count distinct videos with revenue that day
    video_result = await db.execute(
        select(func.count(func.distinct(RevenueEvent.video_record_id)))
        .where(
            RevenueEvent.channel_id == channel_id,
            RevenueEvent.event_date == agg_date,
            RevenueEvent.video_record_id.isnot(None),
        )
    )
    distinct_videos = video_result.scalar() or 0

    # Upsert
    existing = await db.execute(
        select(RevenueDailyAgg).where(
            RevenueDailyAgg.channel_id == channel_id,
            RevenueDailyAgg.agg_date == agg_date,
        )
    )
    agg = existing.scalar_one_or_none()

    if agg:
        agg.total_cents = total_cents
        agg.adsense_cents = adsense_cents
        agg.affiliate_cents = affiliate_cents
        agg.stripe_cents = stripe_cents
        agg.video_count = distinct_videos
    else:
        agg = RevenueDailyAgg(
            id=_new_uuid(),
            channel_id=channel_id,
            agg_date=agg_date,
            total_cents=total_cents,
            adsense_cents=adsense_cents,
            affiliate_cents=affiliate_cents,
            stripe_cents=stripe_cents,
            video_count=distinct_videos,
            created_at=_utcnow(),
        )
        db.add(agg)

    await db.flush()
    return agg


# ── Summary statistics ───────────────────────────────────────────────

async def compute_revenue_summary(
    *,
    channel_id: str,
    days: int = 30,
    db: AsyncSession,
) -> dict:
    """Compute a revenue summary for the last N days.

    Returns::

        {
            "total_cents": int,
            "adsense_cents": int,
            "affiliate_cents": int,
            "stripe_cents": int,
            "manual_cents": int,
            "days_covered": int,
            "daily_average_cents": int,
            "top_videos": [
                {"video_record_id": str, "total_cents": int, "event_count": int},
                ...
            ]
        }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Source breakdown
    source_result = await db.execute(
        select(
            RevenueEvent.source,
            func.sum(RevenueEvent.amount_cents).label("total"),
        )
        .where(
            RevenueEvent.channel_id == channel_id,
            RevenueEvent.event_date >= cutoff,
        )
        .group_by(RevenueEvent.source)
    )
    source_rows = source_result.all()

    breakdown = {"adsense": 0, "affiliate": 0, "stripe": 0, "manual": 0}
    total = 0
    for row in source_rows:
        src, amt = row[0], int(row[1] or 0)
        total += amt
        if src in breakdown:
            breakdown[src] = amt

    # Count distinct days with events
    days_result = await db.execute(
        select(func.count(func.distinct(RevenueEvent.event_date)))
        .where(
            RevenueEvent.channel_id == channel_id,
            RevenueEvent.event_date >= cutoff,
        )
    )
    days_covered = days_result.scalar() or 0

    daily_avg = total // days_covered if days_covered > 0 else 0

    # Top videos by revenue
    top_result = await db.execute(
        select(
            RevenueEvent.video_record_id,
            func.sum(RevenueEvent.amount_cents).label("total"),
            func.count(RevenueEvent.id).label("cnt"),
        )
        .where(
            RevenueEvent.channel_id == channel_id,
            RevenueEvent.event_date >= cutoff,
            RevenueEvent.video_record_id.isnot(None),
        )
        .group_by(RevenueEvent.video_record_id)
        .order_by(func.sum(RevenueEvent.amount_cents).desc())
        .limit(10)
    )
    top_videos = [
        {
            "video_record_id": r[0],
            "total_cents": int(r[1] or 0),
            "event_count": int(r[2] or 0),
        }
        for r in top_result.all()
    ]

    return {
        "total_cents": total,
        "adsense_cents": breakdown["adsense"],
        "affiliate_cents": breakdown["affiliate"],
        "stripe_cents": breakdown["stripe"],
        "manual_cents": breakdown["manual"],
        "days_covered": days_covered,
        "daily_average_cents": daily_avg,
        "top_videos": top_videos,
    }
