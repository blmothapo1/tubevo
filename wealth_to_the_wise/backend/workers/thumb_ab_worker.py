# filepath: backend/workers/thumb_ab_worker.py
"""
Thumbnail A/B testing background worker (Feature 4: Auto A/B Thumbnails).

Periodically rotates active thumbnails for running experiments and
checks whether any experiments have gathered enough impressions to
auto-conclude.

Runs every 6 hours by default. Each cycle:
1. Finds all running experiments
2. Rotates the active variant for each experiment (round-robin)
3. Auto-concludes experiments where all variants have enough impressions
"""

from __future__ import annotations

import asyncio
import logging

from backend.feature_flags import FF_THUMB_AB, is_globally_enabled

logger = logging.getLogger("tubevo.worker.thumb_ab")

# How often to rotate / check (6h by default)
_INTERVAL_SECS = 60 * 60 * 6  # 6 hours


async def _run_thumb_ab_cycle() -> None:
    """Single rotation + auto-conclude pass."""
    from sqlalchemy import select

    from backend.database import async_session_factory
    from backend.models import ThumbExperiment, ThumbVariant
    from backend.services.thumb_ab_service import (
        MIN_IMPRESSIONS_PER_VARIANT,
        conclude_experiment,
        rotate_active_variant,
    )

    async with async_session_factory() as db:
        # Find all running experiments
        result = await db.execute(
            select(ThumbExperiment).where(ThumbExperiment.status == "running")
        )
        experiments = list(result.scalars().all())

        if not experiments:
            logger.debug("Thumb A/B: no running experiments")
            return

        rotated = 0
        concluded = 0

        for exp in experiments:
            try:
                # Rotate the active variant
                new_active = await rotate_active_variant(
                    experiment_id=exp.id, db=db,
                )
                if new_active:
                    rotated += 1

                # Check if all variants have enough impressions to auto-conclude
                var_result = await db.execute(
                    select(ThumbVariant)
                    .where(ThumbVariant.experiment_id == exp.id)
                )
                variants = list(var_result.scalars().all())

                all_sufficient = all(
                    v.impressions >= MIN_IMPRESSIONS_PER_VARIANT
                    for v in variants
                )
                if all_sufficient and len(variants) >= 2:
                    await conclude_experiment(
                        experiment_id=exp.id, db=db, force=False,
                    )
                    concluded += 1
                    logger.info(
                        "Auto-concluded experiment %s (all variants >= %d impressions)",
                        exp.id, MIN_IMPRESSIONS_PER_VARIANT,
                    )

            except Exception:
                logger.exception(
                    "Thumb A/B cycle error for experiment %s", exp.id,
                )

        await db.commit()
        logger.info(
            "Thumb A/B cycle complete: %d experiments, %d rotated, %d auto-concluded",
            len(experiments), rotated, concluded,
        )


async def thumb_ab_loop() -> None:
    """Long-running loop: rotate thumbnails and auto-conclude experiments."""
    logger.info("Thumbnail A/B worker started (interval=%ds)", _INTERVAL_SECS)
    while True:
        try:
            if not is_globally_enabled(FF_THUMB_AB):
                await asyncio.sleep(_INTERVAL_SECS)
                continue

            await _run_thumb_ab_cycle()
            await asyncio.sleep(_INTERVAL_SECS)
        except asyncio.CancelledError:
            logger.info("Thumb A/B worker shutting down")
            break
        except Exception:
            logger.exception("Thumb A/B worker error (will retry in 60s)")
            await asyncio.sleep(60)
