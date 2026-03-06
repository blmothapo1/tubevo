# filepath: backend/workers/voice_clone_worker.py
"""
Voice cloning background worker (Feature 6: Voice Cloning Workflow).

Periodically picks up ``pending`` voice clones and processes them via
the ElevenLabs voice cloning API (POST /v1/voices/add).

Flow:
  1. Find pending clones that have a ``sample_file_key`` (audio uploaded)
  2. Mark as ``processing``
  3. POST the audio file to ElevenLabs ``/v1/voices/add``
  4. On success → mark ``ready`` with the returned ``voice_id``
  5. On failure → mark ``failed`` with the error message

Gated behind FF_VOICE_CLONE.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.database import async_session_factory
from backend.encryption import decrypt_or_raise
from backend.feature_flags import FF_VOICE_CLONE, is_globally_enabled
from backend.models import UserApiKeys, VoiceClone
from backend.services.voice_clone_service import (
    mark_failed,
    mark_processing,
    mark_ready,
)

logger = logging.getLogger("tubevo.worker.voice_clone")

# Check for pending clones every 30 seconds
_INTERVAL_SECS = 30

# ElevenLabs API
_ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


async def _get_elevenlabs_key(user_id: str, db) -> str | None:
    """Retrieve the user's decrypted ElevenLabs API key."""
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == user_id)
    )
    user_keys = result.scalar_one_or_none()
    if not user_keys or not user_keys.elevenlabs_api_key:
        return None
    try:
        return decrypt_or_raise(
            user_keys.elevenlabs_api_key, field="elevenlabs_api_key"
        )
    except Exception:
        return None


async def _clone_voice_via_elevenlabs(
    *,
    api_key: str,
    name: str,
    description: str | None,
    audio_path: Path,
) -> dict:
    """Call ElevenLabs POST /v1/voices/add to create a voice clone.

    Returns dict with ``voice_id`` and optional ``preview_url`` on success.
    Raises RuntimeError with user-friendly message on failure.
    """
    if not audio_path.is_file():
        raise RuntimeError(f"Audio sample not found at {audio_path}")

    # Determine mime type from extension
    mime_map = {
        ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".flac": "audio/flac", ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    mime = mime_map.get(audio_path.suffix.lower(), "audio/webm")

    # Build multipart form for ElevenLabs
    files = {
        "files": (audio_path.name, audio_path.read_bytes(), mime),
    }
    data = {
        "name": name,
    }
    if description:
        data["description"] = description
    # Use labels to tag the source
    data["labels"] = '{"source": "tubevo", "type": "instant_clone"}'

    headers = {
        "xi-api-key": api_key,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{_ELEVENLABS_API_URL}/voices/add",
            headers=headers,
            data=data,
            files=files,
        )

    if resp.status_code == 200:
        body = resp.json()
        voice_id = body.get("voice_id", "")
        if not voice_id:
            raise RuntimeError("ElevenLabs returned 200 but no voice_id in response")
        logger.info("ElevenLabs voice created: voice_id=%s", voice_id)

        # Fetch preview URL (optional — ElevenLabs generates one)
        preview_url = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                detail_resp = await client.get(
                    f"{_ELEVENLABS_API_URL}/voices/{voice_id}",
                    headers=headers,
                )
            if detail_resp.status_code == 200:
                preview_url = detail_resp.json().get("preview_url")
        except Exception:
            pass  # preview URL is nice-to-have, not critical

        return {"voice_id": voice_id, "preview_url": preview_url}

    # Handle errors
    try:
        err_body = resp.json()
        detail = err_body.get("detail", {})
        if isinstance(detail, dict):
            msg = detail.get("message", str(detail))
        else:
            msg = str(detail)
    except Exception:
        msg = resp.text[:500]

    status_code = resp.status_code

    if status_code == 401:
        raise RuntimeError("ElevenLabs API key is invalid. Check your key in Settings → API Keys.")
    elif status_code == 422:
        raise RuntimeError(f"Audio sample rejected by ElevenLabs: {msg}")
    elif status_code == 429:
        raise RuntimeError("ElevenLabs rate limit reached. Please try again in a few minutes.")
    elif status_code == 403:
        raise RuntimeError(
            "Your ElevenLabs plan doesn't support voice cloning. "
            "Upgrade to a paid plan at elevenlabs.io."
        )
    else:
        raise RuntimeError(f"ElevenLabs error (HTTP {status_code}): {msg}")


async def _process_pending_clones() -> int:
    """Pick up pending clones, call ElevenLabs, and update status.

    Returns count of clones processed.
    """
    count = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(VoiceClone)
            .where(
                VoiceClone.status == "pending",
                VoiceClone.sample_file_key != None,  # noqa: E711
            )
            .order_by(VoiceClone.created_at.asc())
            .limit(3)  # Process up to 3 at a time
        )
        pending = list(result.scalars().all())

        if not pending:
            return 0

        for clone in pending:
            try:
                # Get user's ElevenLabs key
                el_key = await _get_elevenlabs_key(clone.user_id, db)
                if not el_key:
                    await mark_failed(
                        clone_id=clone.id,
                        error_message=(
                            "No ElevenLabs API key found. "
                            "Please add your key in Settings → API Keys."
                        ),
                        db=db,
                    )
                    await db.commit()
                    count += 1
                    continue

                # Mark as processing
                await mark_processing(clone_id=clone.id, db=db)
                await db.commit()

                logger.info(
                    "Processing voice clone %s (%s) — calling ElevenLabs…",
                    clone.id, clone.name,
                )

                # Call ElevenLabs
                if not clone.sample_file_key:
                    await mark_failed(
                        clone_id=clone.id,
                        error_message="No audio sample uploaded. Please record or upload an audio sample.",
                        db=db,
                    )
                    await db.commit()
                    count += 1
                    continue
                audio_path = Path(clone.sample_file_key)
                result_data = await _clone_voice_via_elevenlabs(
                    api_key=el_key,
                    name=clone.name,
                    description=clone.description,
                    audio_path=audio_path,
                )

                # Mark as ready
                await mark_ready(
                    clone_id=clone.id,
                    elevenlabs_voice_id=result_data["voice_id"],
                    preview_url=result_data.get("preview_url"),
                    db=db,
                )
                await db.commit()
                count += 1

                logger.info(
                    "✅ Voice clone %s (%s) is READY — EL voice_id=%s",
                    clone.id, clone.name, result_data["voice_id"],
                )

                # Clean up the temp audio file
                try:
                    audio_path.unlink(missing_ok=True)
                except Exception:
                    pass

            except ValueError as exc:
                logger.warning("Skip clone %s: %s", clone.id, exc)
            except RuntimeError as exc:
                # User-friendly error from ElevenLabs
                logger.warning("Voice clone %s failed: %s", clone.id, exc)
                try:
                    await mark_failed(
                        clone_id=clone.id,
                        error_message=str(exc),
                        db=db,
                    )
                    await db.commit()
                    count += 1
                except Exception:
                    logger.exception("Failed to mark clone %s as failed", clone.id)
            except Exception:
                logger.exception("Unexpected error processing clone %s", clone.id)
                try:
                    await mark_failed(
                        clone_id=clone.id,
                        error_message="Unexpected processing error. Please retry.",
                        db=db,
                    )
                    await db.commit()
                    count += 1
                except Exception:
                    logger.exception("Failed to mark clone %s as failed", clone.id)

    return count


async def voice_clone_loop() -> None:
    """Long-running loop: process pending voice clones via ElevenLabs."""
    logger.info("🎙️ Voice clone worker started (interval=%ds)", _INTERVAL_SECS)
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
