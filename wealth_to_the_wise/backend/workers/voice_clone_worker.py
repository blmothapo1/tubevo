# filepath: backend/workers/voice_clone_worker.py
"""
Voice cloning background worker (Feature 6: Voice Cloning Workflow).

Periodically picks up ``pending`` voice clones and processes them.
Currently a simulation loop — when ElevenLabs clone API is wired up,
the worker will POST audio samples and poll for completion.

Gated behind FF_VOICE_CLONE.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from backend.database import async_session_factory
from backend.feature_flags import FF_VOICE_CLONE, is_globally_enabled
from backend.models import VoiceClone
from backend.services.voice_clone_service import mark_failed, mark_processing

logger = logging.getLogger("tubevo.worker.voice_clone")

# Check for pending clones every 60 seconds
_INTERVAL_SECS = 60


async def _process_pending_clones() -> int:
    """Pick up pending clones and move them to processing.

    In a real implementation, this would:
    1. Upload the audio sample to ElevenLabs
    2. Call the clone creation endpoint
    3. Poll for completion
    4. Store the resulting voice ID

    For now, marks clones as processing (a future commit will wire
    the actual ElevenLabs API calls).

    Returns count of clones processed.
    """
    count = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(VoiceClone)
            .where(VoiceClone.status == "pending")
            .order_by(VoiceClone.created_at.asc())
            .limit(5)  # Process up to 5 at a time
        )
        pending = list(result.scalars().all())

        for clone in pending:
            try:
                await mark_processing(clone_id=clone.id, db=db)
                count += 1
                logger.info(
                    "Voice clone %s (%s) moved to processing",
                    clone.id,
                    clone.name,
                )
            except ValueError as exc:
                logger.warning("Skip clone %s: %s", clone.id, exc)
            except Exception:
                logger.exception("Failed to process clone %s", clone.id)
                try:
                    await mark_failed(
                        clone_id=clone.id,
                        error_message="Worker processing error",
                        db=db,
                    )
                except Exception:
                    logger.exception("Failed to mark clone %s as failed", clone.id)

        if count:
            await db.commit()
            logger.info("Processed %d pending voice clone(s)", count)

    return count


async def voice_clone_loop() -> None:
    """Long-running loop: process pending voice clones."""
    logger.info("Voice clone worker started (interval=%ds)", _INTERVAL_SECS)
    while True:
        try:
            if not is_globally_enabled(FF_VOICE_CLONE):
                logger.debug("FF_VOICE_CLONE disabled — sleeping")
                await asyncio.sleep(_INTERVAL_SECS)
                continue

            processed = await _process_pending_clones()
            if processed:
                logger.info("Voice clone cycle: %d processed", processed)
            await asyncio.sleep(_INTERVAL_SECS)
        except asyncio.CancelledError:
            logger.info("Voice clone worker shutting down")
            break
        except Exception:
            logger.exception("Voice clone worker error (will retry in 30s)")
            await asyncio.sleep(30)
