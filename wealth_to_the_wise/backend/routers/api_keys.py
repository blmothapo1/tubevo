# filepath: backend/routers/api_keys.py
"""
User API Keys router — /api/keys

BYOK (Bring Your Own Keys) model: users supply their own OpenAI,
ElevenLabs, and Pexels API keys.  Keys are stored per-user in the DB
**encrypted at rest** and used by the video pipeline at generation time.

Endpoints
---------
GET  /api/keys     — Get current key status (masked hints, not raw keys)
PUT  /api/keys     — Create or update stored API keys
DELETE /api/keys   — Delete all stored API keys
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.encryption import decrypt, encrypt
from backend.models import User, UserApiKeys
from backend.rate_limit import limiter
from backend.schemas import (
    MessageResponse,
    UpdateApiKeysRequest,
    UserApiKeysResponse,
)

logger = logging.getLogger("tubevo.backend.api_keys")

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def _mask_key(encrypted_key: str | None) -> str | None:
    """Decrypt a stored key, then return only the last 4 characters for display."""
    if not encrypted_key:
        return None
    plaintext = decrypt(encrypted_key)
    if not plaintext:
        return None
    if len(plaintext) <= 4:
        return "••••"
    return f"••••{plaintext[-4:]}"


def _has_key(encrypted_key: str | None) -> bool:
    """Return True if the stored (encrypted) value decrypts to a non-empty string."""
    if not encrypted_key:
        return False
    return bool(decrypt(encrypted_key))


# ── GET /api/keys ────────────────────────────────────────────────────

@router.get("", response_model=UserApiKeysResponse)
async def get_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserApiKeysResponse:
    """Return masked hints about which keys are configured."""
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    keys = result.scalar_one_or_none()

    if not keys:
        return UserApiKeysResponse(
            has_openai_key=False,
            has_elevenlabs_key=False,
            has_pexels_key=False,
        )

    return UserApiKeysResponse(
        has_openai_key=_has_key(keys.openai_api_key),
        has_elevenlabs_key=_has_key(keys.elevenlabs_api_key),
        has_pexels_key=_has_key(keys.pexels_api_key),
        elevenlabs_voice_id=keys.elevenlabs_voice_id,
        openai_key_hint=_mask_key(keys.openai_api_key),
        elevenlabs_key_hint=_mask_key(keys.elevenlabs_api_key),
        pexels_key_hint=_mask_key(keys.pexels_api_key),
    )


# ── PUT /api/keys ────────────────────────────────────────────────────

@router.put("", response_model=UserApiKeysResponse)
@limiter.limit("10/minute")
async def update_api_keys(
    request: Request,
    body: UpdateApiKeysRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserApiKeysResponse:
    """Create or update the user's API keys.

    Keys are encrypted with Fernet before storage.
    Only non-None fields in the request body are updated.
    Send an empty string to clear a key.
    """
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    keys = result.scalar_one_or_none()

    if not keys:
        keys = UserApiKeys(user_id=current_user.id)
        db.add(keys)

    # Update only provided fields — encrypt before storing
    if body.openai_api_key is not None:
        keys.openai_api_key = encrypt(body.openai_api_key) if body.openai_api_key else None
    if body.elevenlabs_api_key is not None:
        keys.elevenlabs_api_key = encrypt(body.elevenlabs_api_key) if body.elevenlabs_api_key else None
    if body.elevenlabs_voice_id is not None:
        keys.elevenlabs_voice_id = body.elevenlabs_voice_id or None  # voice_id is not secret
    if body.pexels_api_key is not None:
        keys.pexels_api_key = encrypt(body.pexels_api_key) if body.pexels_api_key else None

    await db.flush()
    await db.refresh(keys)

    logger.info("User %s updated API keys (encrypted at rest).", current_user.email)

    return UserApiKeysResponse(
        has_openai_key=_has_key(keys.openai_api_key),
        has_elevenlabs_key=_has_key(keys.elevenlabs_api_key),
        has_pexels_key=_has_key(keys.pexels_api_key),
        elevenlabs_voice_id=keys.elevenlabs_voice_id,
        openai_key_hint=_mask_key(keys.openai_api_key),
        elevenlabs_key_hint=_mask_key(keys.elevenlabs_api_key),
        pexels_key_hint=_mask_key(keys.pexels_api_key),
    )


# ── DELETE /api/keys ─────────────────────────────────────────────────

@router.delete("", response_model=MessageResponse)
@limiter.limit("5/minute")
async def delete_api_keys(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete all stored API keys for the current user."""
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    keys = result.scalar_one_or_none()

    if keys:
        await db.delete(keys)
        await db.flush()
        logger.info("User %s deleted all API keys.", current_user.email)

    return MessageResponse(message="API keys deleted.")
