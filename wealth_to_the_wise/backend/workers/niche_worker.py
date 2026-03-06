# filepath: backend/workers/niche_worker.py
"""
Niche intelligence background worker (Feature 2: Niche Intel Engine).

Periodically scans each channel's configured niches (from UserPreferences)
and produces NicheSnapshot + NicheTopic rows.

Uses each user's own OpenAI API key (BYOK model).
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from backend.database import async_session_factory
from backend.encryption import decrypt
from backend.feature_flags import FF_NICHE_INTEL, is_globally_enabled
from backend.models import Channel, UserApiKeys, UserPreferences

logger = logging.getLogger("tubevo.worker.niche")

# How often to scan (12h by default)
_INTERVAL_SECS = 60 * 60 * 12  # 12 hours


async def _run_niche_scan_cycle() -> int:
    """Run one scan cycle across all channels with configured niches.

    Returns the number of snapshots created.
    """
    from backend.services.niche_service import analyse_niche, save_niche_snapshot

    created = 0
    async with async_session_factory() as db:
        # Get all channels
        channels_result = await db.execute(select(Channel))
        channels = channels_result.scalars().all()

        for channel in channels:
            # Get user preferences for niches
            prefs_result = await db.execute(
                select(UserPreferences).where(
                    UserPreferences.user_id == channel.user_id
                )
            )
            prefs = prefs_result.scalar_one_or_none()
            if not prefs or not prefs.niches_json:
                continue

            try:
                niches = json.loads(prefs.niches_json)
            except (json.JSONDecodeError, TypeError):
                continue

            if not niches:
                continue

            # Get user's OpenAI key
            keys_result = await db.execute(
                select(UserApiKeys).where(
                    UserApiKeys.user_id == channel.user_id
                )
            )
            user_keys = keys_result.scalar_one_or_none()
            if not user_keys or not user_keys.openai_api_key:
                continue

            openai_key = decrypt(user_keys.openai_api_key)
            if not openai_key:
                continue

            tone_style = prefs.tone_style or "confident, direct, no-fluff educator"
            target_audience = prefs.target_audience or "general audience"

            # Get SerpAPI key for live web trends
            from backend.config import get_settings
            serpapi_key = get_settings().serpapi_api_key

            # Scan each niche (max 3 per channel per cycle to limit cost)
            for niche in niches[:3]:
                try:
                    analysis = await asyncio.to_thread(
                        analyse_niche,
                        niche=niche,
                        openai_api_key=openai_key,
                        tone_style=tone_style,
                        target_audience=target_audience,
                        serpapi_key=serpapi_key,
                    )
                    await save_niche_snapshot(
                        channel_id=channel.id,
                        niche=niche,
                        analysis=analysis,
                        db_session=db,
                    )
                    created += 1
                    logger.info(
                        "Worker: niche scan complete for channel=%s niche=%s",
                        channel.id, niche,
                    )
                except Exception:
                    logger.exception(
                        "Worker: niche scan failed for channel=%s niche=%s",
                        channel.id, niche,
                    )

        if created:
            await db.commit()

    return created


async def niche_loop() -> None:
    """Long-running loop: run niche scans periodically."""
    logger.info("Niche intelligence worker started (interval=%ds)", _INTERVAL_SECS)
    while True:
        try:
            if not is_globally_enabled(FF_NICHE_INTEL):
                await asyncio.sleep(_INTERVAL_SECS)
                continue

            count = await _run_niche_scan_cycle()
            logger.info("Niche worker cycle complete: %d snapshots created", count)
            await asyncio.sleep(_INTERVAL_SECS)
        except asyncio.CancelledError:
            logger.info("Niche worker shutting down")
            break
        except Exception:
            logger.exception("Niche worker error (will retry in 60s)")
            await asyncio.sleep(60)
