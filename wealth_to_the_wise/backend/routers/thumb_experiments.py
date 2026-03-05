# filepath: backend/routers/thumb_experiments.py
"""
Thumbnail A/B testing endpoints (Feature 4: Auto A/B Thumbnails).

All endpoints are gated behind ``FF_THUMB_AB``.

Endpoints
---------
GET   /thumbnails/experiments                      — List experiments
POST  /thumbnails/experiments                      — Create experiment
GET   /thumbnails/experiments/{id}                 — Get experiment details
POST  /thumbnails/experiments/{id}/conclude        — Conclude & pick winner
POST  /thumbnails/experiments/{id}/cancel          — Cancel experiment
POST  /thumbnails/experiments/{id}/rotate          — Manually rotate variant
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.channel_context import get_active_channel
from backend.database import get_db
from backend.feature_flags import FF_THUMB_AB, require_feature
from backend.models import (
    Channel,
    ThumbExperiment,
    ThumbVariant,
    User,
    VideoRecord,
)
from backend.schemas import (
    MessageResponse,
    ThumbConcludeRequest,
    ThumbExperimentCreateRequest,
    ThumbExperimentListResponse,
    ThumbExperimentResponse,
    ThumbVariantResponse,
)

logger = logging.getLogger("tubevo.backend.thumb_experiments")

router = APIRouter(
    prefix="/thumbnails",
    tags=["Thumbnail Experiments"],
    dependencies=[Depends(require_feature(FF_THUMB_AB))],
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


def _serialize_variant(v: ThumbVariant) -> ThumbVariantResponse:
    return ThumbVariantResponse(
        id=v.id,
        experiment_id=v.experiment_id,
        concept=v.concept,
        file_path=v.file_path,
        impressions=v.impressions,
        clicks=v.clicks,
        ctr_pct=v.ctr_pct,
        is_active=v.is_active,
        deployed_at=v.deployed_at,
        created_at=v.created_at,
    )


def _serialize_experiment(
    exp: ThumbExperiment,
    variants: list[ThumbVariant] | None = None,
) -> ThumbExperimentResponse:
    return ThumbExperimentResponse(
        id=exp.id,
        channel_id=exp.channel_id,
        video_record_id=exp.video_record_id,
        status=exp.status,
        started_at=exp.started_at,
        concluded_at=exp.concluded_at,
        winner_variant_id=exp.winner_variant_id,
        rotation_count=exp.rotation_count,
        variants=[_serialize_variant(v) for v in (variants or [])],
        created_at=exp.created_at,
    )


# ── GET /thumbnails/experiments ──────────────────────────────────────

@router.get("/experiments", response_model=ThumbExperimentListResponse)
async def list_experiments(
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
) -> ThumbExperimentListResponse:
    """List thumbnail experiments for the active channel."""
    ch = await _require_channel(channel, current_user, db)

    stmt = (
        select(ThumbExperiment)
        .where(ThumbExperiment.channel_id == ch.id)
        .order_by(ThumbExperiment.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(ThumbExperiment.status == status_filter)

    result = await db.execute(stmt)
    experiments = result.scalars().all()

    items = []
    for exp in experiments:
        var_result = await db.execute(
            select(ThumbVariant)
            .where(ThumbVariant.experiment_id == exp.id)
            .order_by(ThumbVariant.created_at.asc())
        )
        variants = list(var_result.scalars().all())
        items.append(_serialize_experiment(exp, variants))

    return ThumbExperimentListResponse(experiments=items, count=len(items))


# ── POST /thumbnails/experiments ─────────────────────────────────────

@router.post("/experiments", response_model=ThumbExperimentResponse, status_code=201)
async def create_experiment(
    body: ThumbExperimentCreateRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> ThumbExperimentResponse:
    """Create a new thumbnail A/B experiment for a video."""
    ch = await _require_channel(channel, current_user, db)

    # Verify the video exists and belongs to this user
    video_result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == body.video_record_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    video = video_result.scalar_one_or_none()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found.",
        )

    from backend.services.thumb_ab_service import create_experiment as _create

    try:
        experiment, variants = await _create(
            channel_id=ch.id,
            video_record_id=body.video_record_id,
            variants=[v.model_dump() for v in body.variants],
            db=db,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    logger.info(
        "Experiment created: exp=%s video=%s variants=%d channel=%s",
        experiment.id, body.video_record_id, len(variants), ch.id,
    )
    return _serialize_experiment(experiment, variants)


# ── GET /thumbnails/experiments/{id} ─────────────────────────────────

@router.get("/experiments/{experiment_id}", response_model=ThumbExperimentResponse)
async def get_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> ThumbExperimentResponse:
    """Get details of a specific experiment."""
    ch = await _require_channel(channel, current_user, db)

    from backend.services.thumb_ab_service import get_experiment_with_variants

    experiment, variants = await get_experiment_with_variants(
        experiment_id=experiment_id,
        channel_id=ch.id,
        db=db,
    )
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    return _serialize_experiment(experiment, variants)


# ── POST /thumbnails/experiments/{id}/conclude ───────────────────────

@router.post(
    "/experiments/{experiment_id}/conclude",
    response_model=ThumbExperimentResponse,
)
async def conclude_experiment_endpoint(
    experiment_id: str,
    body: ThumbConcludeRequest,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> ThumbExperimentResponse:
    """Conclude an experiment and pick the winner."""
    ch = await _require_channel(channel, current_user, db)

    # Verify ownership
    from backend.services.thumb_ab_service import (
        conclude_experiment as _conclude,
        get_experiment_with_variants,
    )

    exp, _ = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    try:
        experiment, winner = await _conclude(
            experiment_id=experiment_id,
            db=db,
            force=body.force,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Re-fetch variants for response
    _, variants = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )

    logger.info(
        "Experiment concluded: exp=%s winner=%s channel=%s",
        experiment_id,
        winner.concept if winner else "none",
        ch.id,
    )
    return _serialize_experiment(experiment, variants)


# ── POST /thumbnails/experiments/{id}/cancel ─────────────────────────

@router.post(
    "/experiments/{experiment_id}/cancel",
    response_model=ThumbExperimentResponse,
)
async def cancel_experiment_endpoint(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> ThumbExperimentResponse:
    """Cancel a running experiment without picking a winner."""
    ch = await _require_channel(channel, current_user, db)

    from backend.services.thumb_ab_service import (
        cancel_experiment as _cancel,
        get_experiment_with_variants,
    )

    exp, _ = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    try:
        experiment = await _cancel(experiment_id=experiment_id, db=db)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    _, variants = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )

    return _serialize_experiment(experiment, variants)


# ── POST /thumbnails/experiments/{id}/rotate ─────────────────────────

@router.post(
    "/experiments/{experiment_id}/rotate",
    response_model=ThumbExperimentResponse,
)
async def rotate_variant_endpoint(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    channel: Channel | None = Depends(get_active_channel),
    db: AsyncSession = Depends(get_db),
) -> ThumbExperimentResponse:
    """Manually rotate to the next thumbnail variant."""
    ch = await _require_channel(channel, current_user, db)

    from backend.services.thumb_ab_service import (
        get_experiment_with_variants,
        rotate_active_variant,
    )

    exp, _ = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    new_active = await rotate_active_variant(experiment_id=experiment_id, db=db)
    if not new_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate — experiment is not running.",
        )
    await db.commit()

    _, variants = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )
    # Re-fetch experiment for updated rotation_count
    exp_updated, _ = await get_experiment_with_variants(
        experiment_id=experiment_id, channel_id=ch.id, db=db,
    )
    if not exp_updated:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    return _serialize_experiment(exp_updated, variants)
