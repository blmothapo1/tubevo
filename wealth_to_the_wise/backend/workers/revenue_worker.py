# filepath: backend/workers/revenue_worker.py
"""
Revenue ingestion background worker (Feature 3: Revenue Attribution).

Periodically aggregates RevenueEvent rows into RevenueDailyAgg rows
for all channels. This keeps the daily view pre-computed so the
dashboard queries are fast.

Runs every 4 hours by default. Each cycle:
1. Finds all channels with un-aggregated or stale revenue events
2. Re-computes RevenueDailyAgg for each distinct (channel, date) pair
   where events exist in the last 7 days (covers late-arriving data)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from backend.feature_flags import FF_REVENUE, is_globally_enabled

logger = logging.getLogger("tubevo.worker.revenue")

# How often to aggregate (4h by default)
_INTERVAL_SECS = 60 * 60 * 4  # 4 hours

# How many days back to re-aggregate (covers late-arriving events)
_LOOKBACK_DAYS = 7


async def _run_revenue_aggregation_cycle() -> None:
    """Single aggregation pass for all channels."""
    from sqlalchemy import distinct, select

    from backend.database import async_session_factory
    from backend.models import RevenueEvent
    from backend.services.revenue_service import aggregate_daily_revenue

    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    async with async_session_factory() as db:
        # Find all distinct (channel_id, event_date) pairs in the lookback window
        result = await db.execute(
            select(
                distinct(RevenueEvent.channel_id),
                RevenueEvent.event_date,
            )
            .where(RevenueEvent.event_date >= cutoff)
        )
        pairs = result.all()

        if not pairs:
            logger.debug("Revenue aggregation: no events to aggregate")
            return

        aggregated = 0
        for channel_id, event_date in pairs:
            try:
                await aggregate_daily_revenue(
                    channel_id=channel_id,
                    agg_date=event_date,
                    db=db,
                )
                aggregated += 1
            except Exception:
                logger.exception(
                    "Failed to aggregate revenue for channel=%s date=%s",
                    channel_id, event_date,
                )

        await db.commit()
        logger.info(
            "Revenue aggregation complete: %d channel-date pairs processed",
            aggregated,
        )


async def revenue_loop() -> None:
    """Long-running loop: periodically aggregate revenue data."""
    logger.info("Revenue worker started (interval=%ds)", _INTERVAL_SECS)
    while True:
        try:
            if not is_globally_enabled(FF_REVENUE):
                await asyncio.sleep(_INTERVAL_SECS)
                continue

            await _run_revenue_aggregation_cycle()
            await asyncio.sleep(_INTERVAL_SECS)
        except asyncio.CancelledError:
            logger.info("Revenue worker shutting down")
            break
        except Exception:
            logger.exception("Revenue worker error (will retry in 60s)")
            await asyncio.sleep(60)
