# filepath: backend/services/thumb_ab_service.py
"""
Thumbnail A/B Testing service (Feature 4).

Manages the lifecycle of thumbnail experiments:
  - Create an experiment for a video with 2-5 variants
  - Record impressions/clicks per variant (from YouTube Analytics)
  - Determine a winner when statistical confidence is reached
  - Conclude the experiment and set the winning thumbnail

Experiment status flow: ``running`` → ``concluded`` (or ``cancelled``)

Each variant tracks impressions, clicks, and CTR. The winner is the
variant with the highest CTR after a minimum impression threshold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    ThumbExperiment,
    ThumbVariant,
    VideoRecord,
    _new_uuid,
    _utcnow,
)

logger = logging.getLogger("tubevo.backend.thumb_ab_service")

# Minimum impressions per variant before we can conclude
MIN_IMPRESSIONS_PER_VARIANT = 100

# Maximum variants per experiment
MAX_VARIANTS = 5


# ── Create experiment ────────────────────────────────────────────────

async def create_experiment(
    *,
    channel_id: str,
    video_record_id: str,
    variants: list[dict],
    db: AsyncSession,
) -> tuple[ThumbExperiment, list[ThumbVariant]]:
    """Create a new thumbnail A/B experiment.

    Parameters
    ----------
    variants : list[dict]
        Each dict must have ``concept`` (str) and ``file_path`` (str).
        First variant is set as active.

    Returns
    -------
    (experiment, variant_list)

    Raises
    ------
    ValueError
        If the video already has an active experiment, or < 2 variants.
    """
    if len(variants) < 2:
        raise ValueError("An experiment requires at least 2 thumbnail variants")
    if len(variants) > MAX_VARIANTS:
        raise ValueError(f"Maximum {MAX_VARIANTS} variants per experiment")

    # Check for existing active experiment on this video
    existing = await db.execute(
        select(ThumbExperiment).where(
            ThumbExperiment.video_record_id == video_record_id,
            ThumbExperiment.status == "running",
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("This video already has a running experiment")

    now = _utcnow()
    experiment = ThumbExperiment(
        id=_new_uuid(),
        channel_id=channel_id,
        video_record_id=video_record_id,
        status="running",
        started_at=now,
        rotation_count=0,
        created_at=now,
    )
    db.add(experiment)
    await db.flush()

    variant_objects: list[ThumbVariant] = []
    for i, v in enumerate(variants):
        variant = ThumbVariant(
            id=_new_uuid(),
            experiment_id=experiment.id,
            concept=str(v.get("concept", f"variant_{i}"))[:50],
            file_path=str(v.get("file_path", ""))[:2000],
            impressions=0,
            clicks=0,
            ctr_pct=None,
            is_active=(i == 0),  # First variant starts as active
            deployed_at=now if i == 0 else None,
            created_at=now,
        )
        db.add(variant)
        variant_objects.append(variant)

    await db.flush()
    return experiment, variant_objects


# ── Record metrics ───────────────────────────────────────────────────

async def record_variant_metrics(
    *,
    variant_id: str,
    impressions: int,
    clicks: int,
    db: AsyncSession,
) -> ThumbVariant:
    """Update a variant's cumulative impressions and clicks.

    Recalculates CTR percentage.
    """
    result = await db.execute(
        select(ThumbVariant).where(ThumbVariant.id == variant_id)
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise ValueError(f"Variant {variant_id} not found")

    variant.impressions = impressions
    variant.clicks = clicks
    if impressions > 0:
        ctr = (clicks / impressions) * 100
        variant.ctr_pct = f"{ctr:.2f}"
    else:
        variant.ctr_pct = None

    await db.flush()
    return variant


# ── Rotate active variant ────────────────────────────────────────────

async def rotate_active_variant(
    *,
    experiment_id: str,
    db: AsyncSession,
) -> ThumbVariant | None:
    """Rotate to the next variant in round-robin order.

    Returns the newly activated variant, or None if experiment not running.
    """
    exp_result = await db.execute(
        select(ThumbExperiment).where(ThumbExperiment.id == experiment_id)
    )
    experiment = exp_result.scalar_one_or_none()
    if not experiment or experiment.status != "running":
        return None

    # Get all variants ordered by creation
    variants_result = await db.execute(
        select(ThumbVariant)
        .where(ThumbVariant.experiment_id == experiment_id)
        .order_by(ThumbVariant.created_at.asc())
    )
    variants = list(variants_result.scalars().all())
    if len(variants) < 2:
        return None

    # Find currently active variant index
    active_idx = 0
    for i, v in enumerate(variants):
        if v.is_active:
            active_idx = i
            break

    # Deactivate current, activate next
    next_idx = (active_idx + 1) % len(variants)
    now = _utcnow()

    for i, v in enumerate(variants):
        v.is_active = (i == next_idx)
        if i == next_idx:
            v.deployed_at = now

    experiment.rotation_count += 1
    await db.flush()

    return variants[next_idx]


# ── Conclude experiment ──────────────────────────────────────────────

async def conclude_experiment(
    *,
    experiment_id: str,
    db: AsyncSession,
    force: bool = False,
) -> tuple[ThumbExperiment, ThumbVariant | None]:
    """Conclude an experiment and pick the winner.

    The winner is the variant with the highest CTR that has at least
    ``MIN_IMPRESSIONS_PER_VARIANT`` impressions.

    Parameters
    ----------
    force : bool
        If True, conclude even if variants haven't reached the
        minimum impression threshold.

    Returns
    -------
    (experiment, winner_variant_or_none)
    """
    exp_result = await db.execute(
        select(ThumbExperiment).where(ThumbExperiment.id == experiment_id)
    )
    experiment = exp_result.scalar_one_or_none()
    if not experiment:
        raise ValueError("Experiment not found")
    if experiment.status != "running":
        raise ValueError(f"Experiment is already {experiment.status}")

    # Get all variants
    variants_result = await db.execute(
        select(ThumbVariant)
        .where(ThumbVariant.experiment_id == experiment_id)
        .order_by(ThumbVariant.created_at.asc())
    )
    variants = list(variants_result.scalars().all())

    # Check minimum impressions
    if not force:
        for v in variants:
            if v.impressions < MIN_IMPRESSIONS_PER_VARIANT:
                raise ValueError(
                    f"Variant '{v.concept}' has only {v.impressions} impressions "
                    f"(need {MIN_IMPRESSIONS_PER_VARIANT}). Use force=true to override."
                )

    # Find winner by highest CTR
    winner: ThumbVariant | None = None
    best_ctr = -1.0

    for v in variants:
        if v.impressions > 0:
            ctr = v.clicks / v.impressions
            if ctr > best_ctr:
                best_ctr = ctr
                winner = v

    now = _utcnow()
    experiment.status = "concluded"
    experiment.concluded_at = now
    if winner:
        experiment.winner_variant_id = winner.id
        # Set winner as active, deactivate others
        for v in variants:
            v.is_active = (v.id == winner.id)

    await db.flush()
    return experiment, winner


# ── Cancel experiment ────────────────────────────────────────────────

async def cancel_experiment(
    *,
    experiment_id: str,
    db: AsyncSession,
) -> ThumbExperiment:
    """Cancel a running experiment without picking a winner."""
    exp_result = await db.execute(
        select(ThumbExperiment).where(ThumbExperiment.id == experiment_id)
    )
    experiment = exp_result.scalar_one_or_none()
    if not experiment:
        raise ValueError("Experiment not found")
    if experiment.status != "running":
        raise ValueError(f"Experiment is already {experiment.status}")

    experiment.status = "cancelled"
    experiment.concluded_at = _utcnow()
    await db.flush()
    return experiment


# ── Query helpers ────────────────────────────────────────────────────

async def get_experiment_with_variants(
    *,
    experiment_id: str,
    channel_id: str,
    db: AsyncSession,
) -> tuple[ThumbExperiment | None, list[ThumbVariant]]:
    """Load an experiment and its variants, filtered by channel ownership."""
    exp_result = await db.execute(
        select(ThumbExperiment).where(
            ThumbExperiment.id == experiment_id,
            ThumbExperiment.channel_id == channel_id,
        )
    )
    experiment = exp_result.scalar_one_or_none()
    if not experiment:
        return None, []

    variants_result = await db.execute(
        select(ThumbVariant)
        .where(ThumbVariant.experiment_id == experiment.id)
        .order_by(ThumbVariant.created_at.asc())
    )
    variants = list(variants_result.scalars().all())
    return experiment, variants
