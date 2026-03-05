# filepath: backend/routers/revenue.py
"""
Revenue Attribution endpoints (Feature 3: Revenue Dashboard).

All endpoints are gated behind ``FF_REVENUE``.

Endpoints
---------
GET   /revenue/summary           — Revenue summary for last N days
GET   /revenue/events            — List individual revenue events
POST  /revenue/events            — Record a new revenue event
GET   /revenue/daily             — Daily aggregated revenue
POST  /revenue/daily/{date}/agg  — Trigger re-aggregation for a specific date
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.channel_context import get_active_channel
from backend.database import get_db
from backend.feature_flags import FF_REVENUE, require_feature
from backend.models import (
    Channel,
    RevenueEvent,
    RevenueDailyAgg,
    User,
)
from backend.schemas import (
    MessageResponse,
    RevenueDailyAggResponse,
    RevenueDailyListResponse,
    RevenueEventCreateRequest,
    RevenueEventListResponse,
    RevenueEventResponse,
    RevenueSummaryResponse,
)

logger = logging.getLogger("tubevo.backend.revenue")

router = APIRouter(
    prefix="/revenue",
    tags=["Revenue"],
    dependencies=[Depends(require_feature(FF_REVENUE))],
)


# ── Helpers ──────────────────────────────────────────────────────────

async def _require_channel(
    channel: Channel | None,
    current_user: User,
    db: AsyncSession,
) -> Channel:
    """Ensure a channel exists for this user, or 400."""
    if channel:
        return channel

    result = await db.execute(
        select(Channel)
        .where(Channel.user_id == current_user.id)
        .order_by(Channel.created_at.asc())
        .limit(1)
    )
    ch = result.scalar_one_or_none()
    if ch:
        return ch

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No channel found. Please create a channel first.",
    )


def _serialize_event(e: RevenueEvent) -> RevenueEventResponse:
    return RevenueEventResponse(
        id=e.id,
        channel_id=e.channel_id,
        video_record_id=e.video_record_id,
        source=e.source,
        amount_cents=e.amount_cents,
        currency=e.currency,
        event_date=e.event_date,
        external_id=e.external_id,
        created_at=e.created_at,
    )


def _serialize_agg(a: RevenueDailyAgg) -> RevenueDailyAggResponse:
    return RevenueDailyAggResponse(
        id=a.id,
        channel_id=a.channel_id,
        agg_date=a.agg_date,
        total_cents=a.total_cents,
        adsense_cents=a.adsense_cents,
        affiliate_cents=a.affiliate_cents,
        stripe_cents=a.stripe_cents,
        video_count=a.video_count,
        created_at=a.created_at,
    )


# ── GET /revenue/summary ────────────────────────────────────────────

@router.get("/summary", response_model=RevenueSummaryResponse)
async def revenue_summary(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> RevenueSummaryResponse:
    """Get revenue summary for the active channel over the last N days."""
    ch = await _require_channel(channel, current_user, db)

    from backend.services.revenue_service import compute_revenue_summary

    summary = await compute_revenue_summary(
        channel_id=ch.id,
        days=days,
        db=db,
    )

    return RevenueSummaryResponse(
        total_cents=summary["total_cents"],
        adsense_cents=summary["adsense_cents"],
        affiliate_cents=summary["affiliate_cents"],
        stripe_cents=summary["stripe_cents"],
        manual_cents=summary["manual_cents"],
        days_covered=summary["days_covered"],
        daily_average_cents=summary["daily_average_cents"],
        top_videos=summary["top_videos"],
        period_days=days,
    )


# ── GET /revenue/events ─────────────────────────────────────────────

@router.get("/events", response_model=RevenueEventListResponse)
async def list_revenue_events(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    source: str | None = Query(None, pattern=r"^(adsense|affiliate|stripe|manual)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> RevenueEventListResponse:
    """List individual revenue events for the active channel."""
    ch = await _require_channel(channel, current_user, db)

    stmt = (
        select(RevenueEvent)
        .where(RevenueEvent.channel_id == ch.id)
        .order_by(RevenueEvent.event_date.desc(), RevenueEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if source:
        stmt = stmt.where(RevenueEvent.source == source)

    result = await db.execute(stmt)
    events = result.scalars().all()

    return RevenueEventListResponse(
        events=[_serialize_event(e) for e in events],
        count=len(events),
    )


# ── POST /revenue/events ────────────────────────────────────────────

@router.post("/events", response_model=RevenueEventResponse, status_code=201)
async def create_revenue_event(
    body: RevenueEventCreateRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> RevenueEventResponse:
    """Record a new revenue event for the active channel."""
    ch = await _require_channel(channel, current_user, db)

    from backend.services.revenue_service import record_revenue_event

    try:
        event = await record_revenue_event(
            channel_id=ch.id,
            source=body.source,
            amount_cents=body.amount_cents,
            event_date=body.event_date,
            video_record_id=body.video_record_id,
            external_id=body.external_id,
            metadata=body.metadata,
            db=db,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    logger.info(
        "Revenue event recorded: source=%s amount=%d channel=%s",
        body.source, body.amount_cents, ch.id,
    )
    return _serialize_event(event)


# ── GET /revenue/daily ───────────────────────────────────────────────

@router.get("/daily", response_model=RevenueDailyListResponse)
async def daily_revenue(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> RevenueDailyListResponse:
    """Get daily aggregated revenue for the active channel."""
    ch = await _require_channel(channel, current_user, db)

    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    result = await db.execute(
        select(RevenueDailyAgg)
        .where(
            RevenueDailyAgg.channel_id == ch.id,
            RevenueDailyAgg.agg_date >= cutoff,
        )
        .order_by(RevenueDailyAgg.agg_date.desc())
    )
    aggs = result.scalars().all()

    return RevenueDailyListResponse(
        daily=[_serialize_agg(a) for a in aggs],
        count=len(aggs),
    )


# ── POST /revenue/daily/{date}/agg ──────────────────────────────────

@router.post(
    "/daily/{agg_date}/agg",
    response_model=RevenueDailyAggResponse,
    status_code=200,
)
async def trigger_daily_aggregation(
    agg_date: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> RevenueDailyAggResponse:
    """Re-aggregate revenue for a specific date.

    Useful after manually adding events for a past date.
    """
    ch = await _require_channel(channel, current_user, db)

    # Validate date format
    from datetime import datetime as dt
    try:
        dt.strptime(agg_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="agg_date must be YYYY-MM-DD format.",
        )

    from backend.services.revenue_service import aggregate_daily_revenue

    agg = await aggregate_daily_revenue(
        channel_id=ch.id,
        agg_date=agg_date,
        db=db,
    )
    await db.commit()

    logger.info(
        "Daily aggregation triggered: date=%s total=%d channel=%s",
        agg_date, agg.total_cents, ch.id,
    )
    return _serialize_agg(agg)
