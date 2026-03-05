# filepath: backend/routers/niche_intel.py
"""
Niche Intelligence endpoints (Feature 2: Niche Intel Engine).

All endpoints are gated behind ``FF_NICHE_INTEL``.

Endpoints
---------
GET  /niche/snapshots          — List recent niche snapshots for the active channel
POST /niche/scan               — Trigger an on-demand niche analysis
GET  /niche/topics             — Flat list of topic suggestions from latest snapshots
GET  /niche/snapshots/{id}     — Get a single snapshot with its topics
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.channel_context import get_active_channel
from backend.database import get_db
from backend.encryption import decrypt_or_raise
from backend.feature_flags import FF_NICHE_INTEL, require_feature
from backend.models import (
    Channel,
    NicheSnapshot,
    NicheTopic,
    User,
    UserApiKeys,
    UserPreferences,
)
from backend.rate_limit import limiter
from backend.schemas import (
    MessageResponse,
    NicheScanRequest,
    NicheSnapshotListResponse,
    NicheSnapshotResponse,
    NicheTopicListResponse,
    NicheTopicResponse,
)

logger = logging.getLogger("tubevo.backend.niche_intel")

router = APIRouter(
    prefix="/niche",
    tags=["Niche Intelligence"],
    dependencies=[Depends(require_feature(FF_NICHE_INTEL))],
)


# ── Helpers ──────────────────────────────────────────────────────────

def _serialize_topic(t: NicheTopic) -> NicheTopicResponse:
    return NicheTopicResponse(
        id=t.id,
        topic=t.topic,
        estimated_demand=t.estimated_demand,
        competition_level=t.competition_level,
        source=t.source,
        created_at=t.created_at,
    )


def _serialize_snapshot(
    snap: NicheSnapshot,
    topics: list[NicheTopic] | None = None,
) -> NicheSnapshotResponse:
    return NicheSnapshotResponse(
        id=snap.id,
        channel_id=snap.channel_id,
        niche=snap.niche,
        snapshot_date=snap.snapshot_date,
        saturation_score=snap.saturation_score,
        trending_score=snap.trending_score,
        search_volume_est=snap.search_volume_est,
        competitor_count=snap.competitor_count,
        topics=[_serialize_topic(t) for t in (topics or [])],
        created_at=snap.created_at,
    )


async def _require_channel(
    channel: Channel | None,
    current_user: User,
    db: AsyncSession,
) -> Channel:
    """Ensure a channel exists for this user, or 400."""
    if channel:
        return channel

    # Fallback: try to find any channel for this user
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


# ── GET /niche/snapshots ─────────────────────────────────────────────

@router.get("/snapshots", response_model=NicheSnapshotListResponse)
async def list_snapshots(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    niche: str | None = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=100),
) -> NicheSnapshotListResponse:
    """List recent niche snapshots for the active channel."""
    ch = await _require_channel(channel, current_user, db)

    stmt = (
        select(NicheSnapshot)
        .where(NicheSnapshot.channel_id == ch.id)
        .order_by(NicheSnapshot.created_at.desc())
        .limit(limit)
    )
    if niche:
        stmt = stmt.where(NicheSnapshot.niche == niche)

    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    # Bulk-load topics for each snapshot
    items = []
    for snap in snapshots:
        topics_result = await db.execute(
            select(NicheTopic)
            .where(NicheTopic.snapshot_id == snap.id)
            .order_by(NicheTopic.estimated_demand.desc())
        )
        topics = topics_result.scalars().all()
        items.append(_serialize_snapshot(snap, topics))

    return NicheSnapshotListResponse(snapshots=items, count=len(items))


# ── GET /niche/snapshots/{snapshot_id} ───────────────────────────────

@router.get("/snapshots/{snapshot_id}", response_model=NicheSnapshotResponse)
async def get_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> NicheSnapshotResponse:
    """Get a single snapshot with all its topic suggestions."""
    ch = await _require_channel(channel, current_user, db)

    result = await db.execute(
        select(NicheSnapshot).where(
            NicheSnapshot.id == snapshot_id,
            NicheSnapshot.channel_id == ch.id,
        )
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found.")

    topics_result = await db.execute(
        select(NicheTopic)
        .where(NicheTopic.snapshot_id == snap.id)
        .order_by(NicheTopic.estimated_demand.desc())
    )
    topics = topics_result.scalars().all()

    return _serialize_snapshot(snap, topics)


# ── POST /niche/scan ─────────────────────────────────────────────────

@router.post("/scan", response_model=NicheSnapshotResponse, status_code=201)
@limiter.limit("5/hour")
async def trigger_niche_scan(
    request: Request,
    body: NicheScanRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> NicheSnapshotResponse:
    """Trigger an on-demand niche analysis using the user's OpenAI key.

    Calls OpenAI GPT to analyse the niche and returns a snapshot with
    topic suggestions.
    """
    ch = await _require_channel(channel, current_user, db)

    # ── Fetch user's OpenAI key ──────────────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    if not user_keys or not user_keys.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings before running niche scans.",
        )

    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key")

    # ── Fetch user preferences for context ───────────────────────────
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    tone_style = prefs.tone_style if prefs else "confident, direct, no-fluff educator"
    target_audience = prefs.target_audience if prefs else "general audience"

    # ── Run the analysis (sync → thread) ─────────────────────────────
    from backend.services.niche_service import analyse_niche, save_niche_snapshot

    try:
        analysis = await asyncio.to_thread(
            analyse_niche,
            niche=body.niche,
            openai_api_key=openai_key,
            tone_style=tone_style,
            target_audience=target_audience,
        )
    except ValueError as exc:
        logger.warning("Niche scan failed for user %s: %s", current_user.email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Niche analysis failed: {exc}",
        )

    # ── Persist results ──────────────────────────────────────────────
    snapshot, topics = await save_niche_snapshot(
        channel_id=ch.id,
        niche=body.niche,
        analysis=analysis,
        db_session=db,
    )

    logger.info(
        "Niche scan complete: niche=%s topics=%d user=%s channel=%s",
        body.niche, len(topics), current_user.email, ch.id,
    )
    return _serialize_snapshot(snapshot, topics)


# ── GET /niche/topics ────────────────────────────────────────────────

@router.get("/topics", response_model=NicheTopicListResponse)
async def list_suggested_topics(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(30, ge=1, le=100),
) -> NicheTopicListResponse:
    """Get a flat list of topic suggestions from the most recent snapshots.

    Returns topics sorted by estimated demand (highest first),
    deduplicated by topic text.
    """
    ch = await _require_channel(channel, current_user, db)

    # Get recent snapshot IDs for this channel (last 5)
    snap_result = await db.execute(
        select(NicheSnapshot.id)
        .where(NicheSnapshot.channel_id == ch.id)
        .order_by(NicheSnapshot.created_at.desc())
        .limit(5)
    )
    snapshot_ids = [row[0] for row in snap_result.all()]

    if not snapshot_ids:
        return NicheTopicListResponse(topics=[], count=0)

    # Fetch all topics from these snapshots
    topics_result = await db.execute(
        select(NicheTopic)
        .where(NicheTopic.snapshot_id.in_(snapshot_ids))
        .order_by(NicheTopic.estimated_demand.desc())
    )
    all_topics = topics_result.scalars().all()

    # Deduplicate by topic text (keep highest demand version)
    seen: set[str] = set()
    unique_topics: list[NicheTopic] = []
    for t in all_topics:
        key = t.topic.lower().strip()
        if key not in seen:
            seen.add(key)
            unique_topics.append(t)
        if len(unique_topics) >= limit:
            break

    items = [_serialize_topic(t) for t in unique_topics]
    return NicheTopicListResponse(topics=items, count=len(items))
