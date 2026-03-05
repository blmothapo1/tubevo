# filepath: backend/workers/competitor_worker.py
"""
Competitor monitoring background worker (Feature 5: Spy Mode).

Periodically iterates over all active competitor channels and records
a daily snapshot.  Currently stores a "self-reported" snapshot (the
latest subscriber_count from the CompetitorChannel row) as a baseline.
When YouTube Data API integration is wired up, the worker will fetch
live stats.

Gated behind FF_COMPETITOR_SPY.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from backend.database import async_session_factory
from backend.feature_flags import FF_COMPETITOR_SPY, is_globally_enabled
from backend.models import CompetitorChannel
from backend.services.competitor_service import record_snapshot

logger = logging.getLogger("tubevo.worker.competitor")

# How often to check (24h by default — competitors don't change fast)
_INTERVAL_SECS = 60 * 60 * 24  # 24 hours


async def _run_competitor_cycle() -> int:
    """Snapshot all active competitors.  Returns count of snapshots taken."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(CompetitorChannel).where(
                CompetitorChannel.is_active == True,  # noqa: E712
            )
        )
        competitors = list(result.scalars().all())

        for comp in competitors:
            try:
                # Baseline snapshot from stored metadata.
                # Phase 5+: replace with live YouTube Data API call.
                await record_snapshot(
                    competitor_id=comp.id,
                    snapshot_date=today,
                    subscriber_count=comp.subscriber_count or 0,
                    total_views=0,
                    video_count=0,
                    avg_views_per_video=0,
                    db=db,
                )
                count += 1
            except Exception:
                logger.exception(
                    "Failed to snapshot competitor %s (%s)",
                    comp.id,
                    comp.name,
                )

        if count:
            await db.commit()
            logger.info("Recorded %d competitor snapshot(s) for %s", count, today)

    return count


async def competitor_loop() -> None:
    """Long-running loop: snapshot competitor channels once per day."""
    logger.info("Competitor worker started (interval=%ds)", _INTERVAL_SECS)
    while True:
        try:
            if not is_globally_enabled(FF_COMPETITOR_SPY):
                logger.debug("FF_COMPETITOR_SPY disabled — sleeping")
                await asyncio.sleep(_INTERVAL_SECS)
                continue

            taken = await _run_competitor_cycle()
            logger.info("Competitor cycle complete — %d snapshots", taken)
            await asyncio.sleep(_INTERVAL_SECS)
        except asyncio.CancelledError:
            logger.info("Competitor worker shutting down")
            break
        except Exception:
            logger.exception("Competitor worker error (will retry in 60s)")
            await asyncio.sleep(60)
