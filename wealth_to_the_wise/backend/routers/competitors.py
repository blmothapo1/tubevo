# filepath: backend/routers/competitors.py
"""
Competitor monitoring endpoints (Feature 5: Spy Mode).

All endpoints are gated behind ``FF_COMPETITOR_SPY``.

Endpoints
---------
GET    /competitors                           — List tracked competitors
POST   /competitors                           — Add a competitor to track
GET    /competitors/{id}                      — Get competitor details + growth
DELETE /competitors/{id}                      — Stop tracking a competitor
GET    /competitors/{id}/snapshots            — Historical snapshots
POST   /competitors/{id}/snapshots            — Record a snapshot (manual)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.channel_context import get_active_channel
from backend.database import get_db
from backend.feature_flags import FF_COMPETITOR_SPY, require_feature
from backend.models import Channel, User
from backend.schemas import (
    CompetitorAddRequest,
    CompetitorGrowthResponse,
    CompetitorListResponse,
    CompetitorResponse,
    CompetitorSnapshotCreateRequest,
    CompetitorSnapshotListResponse,
    CompetitorSnapshotResponse,
    MessageResponse,
)
from backend.services.competitor_service import (
    add_competitor,
    compute_growth_summary,
    get_competitor,
    list_competitors,
    list_snapshots,
    record_snapshot,
    remove_competitor,
)

logger = logging.getLogger("tubevo.backend.competitors")

router = APIRouter(
    prefix="/competitors",
    tags=["Competitors"],
    dependencies=[Depends(require_feature(FF_COMPETITOR_SPY))],
)


# ── Helpers ──────────────────────────────────────────────────────────

def _require_channel(channel: Channel | None) -> Channel:
    """Raise 400 if the user has no active channel."""
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active channel. Create a channel first.",
        )
    return channel


# ── LIST competitors ─────────────────────────────────────────────────

@router.get(
    "",
    response_model=CompetitorListResponse,
    summary="List tracked competitors",
)
async def list_competitors_endpoint(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    competitors = await list_competitors(
        channel_id=ch.id,
        include_inactive=include_inactive,
        db=db,
    )
    return CompetitorListResponse(
        competitors=[CompetitorResponse.model_validate(c) for c in competitors],
        count=len(competitors),
    )


# ── ADD competitor ───────────────────────────────────────────────────

@router.post(
    "",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a competitor to track",
)
async def add_competitor_endpoint(
    body: CompetitorAddRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    try:
        competitor = await add_competitor(
            channel_id=ch.id,
            youtube_channel_id=body.youtube_channel_id,
            name=body.name,
            subscriber_count=body.subscriber_count,
            db=db,
        )
        await db.commit()
        await db.refresh(competitor)
        return CompetitorResponse.model_validate(competitor)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ── GET single competitor + growth ───────────────────────────────────

@router.get(
    "/{competitor_id}",
    summary="Get competitor details and growth summary",
)
async def get_competitor_endpoint(
    competitor_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    competitor = await get_competitor(
        competitor_id=competitor_id,
        channel_id=ch.id,
        db=db,
    )
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competitor not found",
        )

    growth = await compute_growth_summary(
        competitor_id=competitor_id,
        db=db,
    )
    return {
        "competitor": CompetitorResponse.model_validate(competitor),
        "growth": CompetitorGrowthResponse(**growth),
    }


# ── DELETE competitor ────────────────────────────────────────────────

@router.delete(
    "/{competitor_id}",
    response_model=MessageResponse,
    summary="Stop tracking a competitor",
)
async def remove_competitor_endpoint(
    competitor_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    try:
        await remove_competitor(
            competitor_id=competitor_id,
            channel_id=ch.id,
            db=db,
        )
        await db.commit()
        return MessageResponse(message="Competitor removed")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ── LIST snapshots ───────────────────────────────────────────────────

@router.get(
    "/{competitor_id}/snapshots",
    response_model=CompetitorSnapshotListResponse,
    summary="Get historical snapshots for a competitor",
)
async def list_snapshots_endpoint(
    competitor_id: str,
    limit: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    # Validate competitor belongs to this channel
    competitor = await get_competitor(
        competitor_id=competitor_id,
        channel_id=ch.id,
        db=db,
    )
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competitor not found",
        )

    snapshots = await list_snapshots(
        competitor_id=competitor_id,
        limit=limit,
        db=db,
    )
    return CompetitorSnapshotListResponse(
        snapshots=[CompetitorSnapshotResponse.model_validate(s) for s in snapshots],
        count=len(snapshots),
    )


# ── RECORD snapshot (manual) ────────────────────────────────────────

@router.post(
    "/{competitor_id}/snapshots",
    response_model=CompetitorSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a competitor snapshot (manual ingestion)",
)
async def record_snapshot_endpoint(
    competitor_id: str,
    body: CompetitorSnapshotCreateRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
):
    ch = _require_channel(channel)
    # Validate competitor belongs to this channel
    competitor = await get_competitor(
        competitor_id=competitor_id,
        channel_id=ch.id,
        db=db,
    )
    if not competitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competitor not found",
        )

    snapshot = await record_snapshot(
        competitor_id=competitor_id,
        snapshot_date=body.snapshot_date,
        subscriber_count=body.subscriber_count,
        total_views=body.total_views,
        video_count=body.video_count,
        avg_views_per_video=body.avg_views_per_video,
        recent_videos=body.recent_videos,
        top_tags=body.top_tags,
        db=db,
    )
    await db.commit()
    await db.refresh(snapshot)
    return CompetitorSnapshotResponse.model_validate(snapshot)
