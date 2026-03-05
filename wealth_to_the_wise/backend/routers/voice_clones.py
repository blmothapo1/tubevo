# filepath: backend/routers/voice_clones.py
"""
Voice cloning endpoints (Feature 6: Voice Cloning Workflow).

All endpoints are gated behind ``FF_VOICE_CLONE``.

Endpoints
---------
GET    /voice-clones              — List all voice clones
POST   /voice-clones              — Create a voice clone
GET    /voice-clones/{id}         — Get clone details
DELETE /voice-clones/{id}         — Soft-delete a clone
POST   /voice-clones/{id}/retry   — Retry a failed clone
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
