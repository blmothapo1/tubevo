# filepath: backend/services/voice_clone_service.py
"""
Voice Cloning service (Feature 6: Voice Cloning Workflow).

Manages the lifecycle of user voice clones:
  - Create a voice clone record (pending → processing → ready / failed)
  - List / retrieve voice clones
  - Mark clones as processing, ready, or failed
  - Soft-delete clones

The actual ElevenLabs API call is delegated to the background worker.
This service handles the database state machine only.

Status flow: ``pending`` → ``processing`` → ``ready`` (or ``failed``) → ``deleted``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import VoiceClone, _new_uuid, _utcnow

logger = logging.getLogger("tubevo.backend.voice_clone_service")

# Limits
MAX_CLONES_PER_USER = 5

# Valid statuses
VALID_STATUSES = {"pending", "processing", "ready", "failed", "deleted"}


# ── Create clone ─────────────────────────────────────────────────────

async def create_voice_clone(
    *,
    user_id: str,
    name: str,
    description: str | None = None,
    sample_file_key: str | None = None,
    sample_duration_secs: int | None = None,
    labels: dict | None = None,
    db: AsyncSession,
) -> VoiceClone:
    """Create a new voice clone record in ``pending`` status.

    Raises
    ------
    ValueError
        If the user has reached MAX_CLONES_PER_USER or name is empty.
    """
    name = name.strip()
    if not name:
        raise ValueError("Voice clone name is required")

    # Check limit (exclude deleted)
    count_result = await db.execute(
        select(func.count()).select_from(VoiceClone).where(
            VoiceClone.user_id == user_id,
            VoiceClone.status != "deleted",
        )
    )
    current_count = count_result.scalar() or 0
    if current_count >= MAX_CLONES_PER_USER:
        raise ValueError(
            f"Maximum {MAX_CLONES_PER_USER} voice clones per user. "
            f"Delete one before creating another."
        )

    now = _utcnow()
    clone = VoiceClone(
        id=_new_uuid(),
        user_id=user_id,
        name=name,
        description=description,
        sample_file_key=sample_file_key,
        sample_duration_secs=sample_duration_secs,
        labels_json=json.dumps(labels) if labels else None,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(clone)
    await db.flush()
    return clone


# ── List clones ──────────────────────────────────────────────────────

async def list_voice_clones(
    *,
    user_id: str,
    include_deleted: bool = False,
    db: AsyncSession,
) -> list[VoiceClone]:
    """Return all voice clones for a user."""
    query = (
        select(VoiceClone)
        .where(VoiceClone.user_id == user_id)
        .order_by(VoiceClone.created_at.desc())
    )
    if not include_deleted:
        query = query.where(VoiceClone.status != "deleted")
    result = await db.execute(query)
    return list(result.scalars().all())


# ── Get single clone ────────────────────────────────────────────────

async def get_voice_clone(
    *,
    clone_id: str,
    user_id: str,
    db: AsyncSession,
) -> VoiceClone | None:
    """Return a single voice clone, or None."""
    result = await db.execute(
        select(VoiceClone).where(
            VoiceClone.id == clone_id,
            VoiceClone.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


# ── Transition helpers ───────────────────────────────────────────────

async def mark_processing(
    *,
    clone_id: str,
    db: AsyncSession,
) -> VoiceClone:
    """Move clone from ``pending`` to ``processing``.

    Raises ValueError if clone not found or not in ``pending``.
    """
    result = await db.execute(
        select(VoiceClone).where(VoiceClone.id == clone_id)
    )
    clone = result.scalar_one_or_none()
    if not clone:
        raise ValueError(f"Voice clone {clone_id} not found")
    if clone.status != "pending":
        raise ValueError(
            f"Cannot process clone in '{clone.status}' status (expected 'pending')"
        )
    clone.status = "processing"
    clone.updated_at = _utcnow()
    await db.flush()
    return clone


async def mark_ready(
    *,
    clone_id: str,
    elevenlabs_voice_id: str,
    preview_url: str | None = None,
    db: AsyncSession,
) -> VoiceClone:
    """Move clone to ``ready`` and store the ElevenLabs voice ID.

    Raises ValueError if clone not found or not in ``processing``.
    """
    result = await db.execute(
        select(VoiceClone).where(VoiceClone.id == clone_id)
    )
    clone = result.scalar_one_or_none()
    if not clone:
        raise ValueError(f"Voice clone {clone_id} not found")
    if clone.status != "processing":
        raise ValueError(
            f"Cannot mark ready clone in '{clone.status}' status (expected 'processing')"
        )
    clone.status = "ready"
    clone.elevenlabs_voice_id = elevenlabs_voice_id
    clone.preview_url = preview_url
    clone.updated_at = _utcnow()
    await db.flush()
    return clone


async def mark_failed(
    *,
    clone_id: str,
    error_message: str = "Unknown error",
    db: AsyncSession,
) -> VoiceClone:
    """Move clone to ``failed`` and store the error message.

    Raises ValueError if clone not found or not in ``pending``/``processing``.
    """
    result = await db.execute(
        select(VoiceClone).where(VoiceClone.id == clone_id)
    )
    clone = result.scalar_one_or_none()
    if not clone:
        raise ValueError(f"Voice clone {clone_id} not found")
    if clone.status not in ("pending", "processing"):
        raise ValueError(
            f"Cannot fail clone in '{clone.status}' status"
        )
    clone.status = "failed"
    clone.error_message = error_message
    clone.updated_at = _utcnow()
    await db.flush()
    return clone


# ── Delete clone ─────────────────────────────────────────────────────

async def delete_voice_clone(
    *,
    clone_id: str,
    user_id: str,
    db: AsyncSession,
) -> VoiceClone:
    """Soft-delete a voice clone.

    Raises ValueError if not found, doesn't belong to user, or already deleted.
    """
    result = await db.execute(
        select(VoiceClone).where(
            VoiceClone.id == clone_id,
            VoiceClone.user_id == user_id,
        )
    )
    clone = result.scalar_one_or_none()
    if not clone:
        raise ValueError("Voice clone not found")
    if clone.status == "deleted":
        raise ValueError("Voice clone is already deleted")

    clone.status = "deleted"
    clone.updated_at = _utcnow()
    await db.flush()
    return clone


# ── Retry clone ──────────────────────────────────────────────────────

async def retry_voice_clone(
    *,
    clone_id: str,
    user_id: str,
    db: AsyncSession,
) -> VoiceClone:
    """Reset a failed clone back to ``pending`` for re-processing.

    Raises ValueError if not found or not in ``failed`` status.
    """
    result = await db.execute(
        select(VoiceClone).where(
            VoiceClone.id == clone_id,
            VoiceClone.user_id == user_id,
        )
    )
    clone = result.scalar_one_or_none()
    if not clone:
        raise ValueError("Voice clone not found")
    if clone.status != "failed":
        raise ValueError(
            f"Can only retry failed clones (current status: '{clone.status}')"
        )

    clone.status = "pending"
    clone.error_message = None
    clone.updated_at = _utcnow()
    await db.flush()
    return clone
