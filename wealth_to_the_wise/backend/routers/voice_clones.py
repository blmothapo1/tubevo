# filepath: backend/routers/voice_clones.py
"""
Voice cloning endpoints (Feature 6: Voice Cloning Workflow).

All endpoints are gated behind ``FF_VOICE_CLONE``.

Endpoints
---------
GET    /voice-clones                  — List all voice clones
POST   /voice-clones                  — Create a voice clone
POST   /voice-clones/upload-sample    — Upload audio sample file
GET    /voice-clones/{id}             — Get clone details
DELETE /voice-clones/{id}             — Soft-delete a clone
POST   /voice-clones/{id}/retry       — Retry a failed clone
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.feature_flags import FF_VOICE_CLONE, require_feature
from backend.models import User
from backend.schemas import (
    MessageResponse,
    VoiceCloneCreateRequest,
    VoiceCloneListResponse,
    VoiceCloneResponse,
)
from backend.services.voice_clone_service import (
    create_voice_clone,
    delete_voice_clone,
    get_voice_clone,
    list_voice_clones,
    retry_voice_clone,
)

logger = logging.getLogger("tubevo.backend.voice_clones")

router = APIRouter(
    prefix="/voice-clones",
    tags=["Voice Clones"],
    dependencies=[Depends(require_feature(FF_VOICE_CLONE))],
)


# ── LIST voice clones ───────────────────────────────────────────────

@router.get(
    "",
    response_model=VoiceCloneListResponse,
    summary="List all voice clones",
)
async def list_clones_endpoint(
    include_deleted: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clones = await list_voice_clones(
        user_id=current_user.id,
        include_deleted=include_deleted,
        db=db,
    )
    return VoiceCloneListResponse(
        voice_clones=[VoiceCloneResponse.model_validate(c) for c in clones],
        count=len(clones),
    )


# ── UPLOAD audio sample ─────────────────────────────────────────────

# Max 25 MB audio upload
_MAX_AUDIO_SIZE = 25 * 1024 * 1024
_ALLOWED_MIMETYPES = {
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3", "audio/mp4",
    "audio/wav", "audio/x-wav", "audio/flac", "audio/aac",
    "video/webm",  # Chrome records webm with video mimetype sometimes
}
_VOICE_SAMPLES_DIR = Path(tempfile.gettempdir()) / "tubevo_voice_samples"


@router.post(
    "/upload-sample",
    summary="Upload an audio sample for voice cloning",
)
async def upload_sample(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Accept an audio file upload and save it to a local temp path.

    Returns ``{ file_key, duration_secs }`` so the caller can pass them
    to ``POST /voice-clones`` to create the clone record.

    The worker reads the file from ``file_key`` when it processes the
    clone via ElevenLabs.
    """
    # Validate content type
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct not in _ALLOWED_MIMETYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {ct}. Upload WebM, MP3, WAV, FLAC, or OGG.",
        )

    # Read and check size
    contents = await file.read()
    if len(contents) > _MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file too large ({len(contents) / (1024*1024):.1f} MB). Maximum is 25 MB.",
        )
    if len(contents) < 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file appears empty or too small.",
        )

    # Determine extension from content type
    ext_map = {
        "audio/webm": ".webm", "video/webm": ".webm", "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a",
        "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/flac": ".flac",
        "audio/aac": ".aac",
    }
    ext = ext_map.get(ct, ".webm")

    # Save to temp dir keyed by user
    _VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    file_key = f"voice_samples/{current_user.id}/{uuid.uuid4().hex}{ext}"
    dest = _VOICE_SAMPLES_DIR / file_key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(contents)

    # Estimate duration (rough: assume ~16 kbps for webm/opus, adjust for others)
    bitrate_map = {".webm": 16_000, ".ogg": 16_000, ".mp3": 128_000, ".wav": 1_411_200, ".flac": 700_000, ".m4a": 128_000, ".aac": 128_000}
    bps = bitrate_map.get(ext, 32_000)
    estimated_secs = max(1, int((len(contents) * 8) / bps))

    logger.info(
        "Voice sample uploaded: user=%s size=%d ext=%s est_secs=%d key=%s",
        current_user.id, len(contents), ext, estimated_secs, file_key,
    )

    return {
        "file_key": str(dest),  # absolute path — worker reads from here
        "duration_secs": estimated_secs,
    }


# ── CREATE voice clone ──────────────────────────────────────────────

@router.post(
    "",
    response_model=VoiceCloneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a voice clone",
)
async def create_clone_endpoint(
    body: VoiceCloneCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        clone = await create_voice_clone(
            user_id=current_user.id,
            name=body.name,
            description=body.description,
            sample_file_key=body.sample_file_key,
            sample_duration_secs=body.sample_duration_secs,
            labels=body.labels,
            db=db,
        )
        await db.commit()
        await db.refresh(clone)
        return VoiceCloneResponse.model_validate(clone)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ── GET single voice clone ──────────────────────────────────────────

@router.get(
    "/{clone_id}",
    response_model=VoiceCloneResponse,
    summary="Get voice clone details",
)
async def get_clone_endpoint(
    clone_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clone = await get_voice_clone(
        clone_id=clone_id,
        user_id=current_user.id,
        db=db,
    )
    if not clone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice clone not found",
        )
    return VoiceCloneResponse.model_validate(clone)


# ── DELETE voice clone ───────────────────────────────────────────────

@router.delete(
    "/{clone_id}",
    response_model=MessageResponse,
    summary="Soft-delete a voice clone",
)
async def delete_clone_endpoint(
    clone_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_voice_clone(
            clone_id=clone_id,
            user_id=current_user.id,
            db=db,
        )
        await db.commit()
        return MessageResponse(message="Voice clone deleted")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ── RETRY failed voice clone ────────────────────────────────────────

@router.post(
    "/{clone_id}/retry",
    response_model=VoiceCloneResponse,
    summary="Retry a failed voice clone",
)
async def retry_clone_endpoint(
    clone_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        clone = await retry_voice_clone(
            clone_id=clone_id,
            user_id=current_user.id,
            db=db,
        )
        await db.commit()
        await db.refresh(clone)
        return VoiceCloneResponse.model_validate(clone)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
