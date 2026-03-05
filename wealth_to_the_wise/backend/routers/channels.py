# filepath: backend/routers/channels.py
"""
Channel management endpoints (Feature 1: Multi-Channel).

All endpoints are gated behind ``FF_MULTI_CHANNEL``.

Endpoints
---------
GET    /channels                        — List all channels
POST   /channels                        — Create a new channel
GET    /channels/{id}                   — Get a single channel
PATCH  /channels/{id}                   — Update channel name / set as default
DELETE /channels/{id}                   — Delete a channel
POST   /channels/{id}/link-youtube      — Connect channel to a YouTube OAuth token
POST   /channels/{id}/set-default       — Shortcut: mark a channel as default
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.feature_flags import FF_MULTI_CHANNEL, require_feature
from backend.models import Channel, OAuthToken, User, _new_uuid, _utcnow
from backend.rate_limit import limiter
from backend.schemas import (
    ChannelCreateRequest,
    ChannelListResponse,
    ChannelResponse,
    ChannelUpdateRequest,
    MessageResponse,
)

logger = logging.getLogger("tubevo.backend.channels")

router = APIRouter(
    prefix="/channels",
    tags=["Channels"],
    dependencies=[Depends(require_feature(FF_MULTI_CHANNEL))],
)

# ── Limits ───────────────────────────────────────────────────────────

MAX_CHANNELS_PER_USER = 10


# ── Helpers ──────────────────────────────────────────────────────────

def _serialize_channel(ch: Channel, oauth: OAuthToken | None = None) -> ChannelResponse:
    """Convert a Channel ORM object to a response schema."""
    yt_connected = ch.oauth_token_id is not None
    channel_title = None
    if oauth:
        channel_title = oauth.channel_title
    return ChannelResponse(
        id=ch.id,
        name=ch.name,
        platform=ch.platform,
        youtube_channel_id=ch.youtube_channel_id,
        oauth_token_id=ch.oauth_token_id,
        is_default=ch.is_default,
        youtube_connected=yt_connected,
        channel_title=channel_title,
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )


async def _get_channel_or_404(
    channel_id: str,
    user_id: str,
    db: AsyncSession,
) -> Channel:
    """Fetch a channel owned by the user, or raise 404."""
    result = await db.execute(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.user_id == user_id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found.",
        )
    return channel


async def _clear_default_flag(user_id: str, db: AsyncSession) -> None:
    """Un-mark any existing default channel for this user."""
    from sqlalchemy import update

    await db.execute(
        update(Channel)
        .where(Channel.user_id == user_id, Channel.is_default.is_(True))
        .values(is_default=False)
    )


# ── GET /channels ────────────────────────────────────────────────────

@router.get("", response_model=ChannelListResponse)
async def list_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelListResponse:
    """List all channels for the current user."""
    result = await db.execute(
        select(Channel)
        .where(Channel.user_id == current_user.id)
        .order_by(Channel.is_default.desc(), Channel.created_at.asc())
    )
    channels = result.scalars().all()

    # Bulk-fetch associated OAuthTokens for channel_title display
    token_ids = [ch.oauth_token_id for ch in channels if ch.oauth_token_id]
    oauth_map: dict[str, OAuthToken] = {}
    if token_ids:
        tok_result = await db.execute(
            select(OAuthToken).where(OAuthToken.id.in_(token_ids))
        )
        for tok in tok_result.scalars().all():
            oauth_map[tok.id] = tok

    items = [
        _serialize_channel(ch, oauth_map.get(ch.oauth_token_id) if ch.oauth_token_id else None)
        for ch in channels
    ]
    return ChannelListResponse(channels=items, count=len(items))


# ── POST /channels ───────────────────────────────────────────────────

@router.post("", response_model=ChannelResponse, status_code=201)
@limiter.limit("10/hour")
async def create_channel(
    request: Request,
    body: ChannelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Create a new channel.

    The first channel created is automatically marked as default.
    """
    # Enforce per-user limit
    count_result = await db.execute(
        select(func.count()).select_from(Channel).where(
            Channel.user_id == current_user.id
        )
    )
    existing_count = count_result.scalar() or 0
    if existing_count >= MAX_CHANNELS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_CHANNELS_PER_USER} channels per account.",
        )

    # If this is the user's first channel, make it default
    is_first = existing_count == 0

    channel = Channel(
        id=_new_uuid(),
        user_id=current_user.id,
        name=body.name,
        platform=body.platform,
        is_default=is_first,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(channel)
    await db.flush()

    logger.info(
        "Channel created: id=%s name=%s user=%s default=%s",
        channel.id, channel.name, current_user.email, is_first,
    )
    return _serialize_channel(channel)


# ── GET /channels/{channel_id} ───────────────────────────────────────

@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Get a single channel by ID."""
    channel = await _get_channel_or_404(channel_id, current_user.id, db)

    oauth = None
    if channel.oauth_token_id:
        tok_result = await db.execute(
            select(OAuthToken).where(OAuthToken.id == channel.oauth_token_id)
        )
        oauth = tok_result.scalar_one_or_none()

    return _serialize_channel(channel, oauth)


# ── PATCH /channels/{channel_id} ────────────────────────────────────

@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: str,
    body: ChannelUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Update channel name and/or set as default."""
    channel = await _get_channel_or_404(channel_id, current_user.id, db)

    if body.name is not None:
        channel.name = body.name

    if body.is_default is True:
        # Clear all other defaults, then set this one
        await _clear_default_flag(current_user.id, db)
        channel.is_default = True
    elif body.is_default is False:
        channel.is_default = False

    channel.updated_at = _utcnow()
    db.add(channel)
    await db.flush()

    logger.info("Channel updated: id=%s user=%s", channel.id, current_user.email)
    return _serialize_channel(channel)


# ── DELETE /channels/{channel_id} ────────────────────────────────────

@router.delete("/{channel_id}", response_model=MessageResponse)
async def delete_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a channel.

    Cannot delete the default channel if it's the only one.
    """
    channel = await _get_channel_or_404(channel_id, current_user.id, db)

    # Count remaining channels
    count_result = await db.execute(
        select(func.count()).select_from(Channel).where(
            Channel.user_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    if channel.is_default and total <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your only channel. Create another one first.",
        )

    was_default = channel.is_default
    await db.delete(channel)
    await db.flush()

    # If deleted channel was default, promote the oldest remaining
    if was_default:
        oldest_result = await db.execute(
            select(Channel)
            .where(Channel.user_id == current_user.id)
            .order_by(Channel.created_at.asc())
            .limit(1)
        )
        oldest = oldest_result.scalar_one_or_none()
        if oldest:
            oldest.is_default = True
            db.add(oldest)
            await db.flush()
            logger.info(
                "Promoted channel %s as new default for user %s",
                oldest.id, current_user.email,
            )

    logger.info("Channel deleted: id=%s user=%s", channel_id, current_user.email)
    return MessageResponse(message="Channel deleted successfully.")


# ── POST /channels/{channel_id}/set-default ──────────────────────────

@router.post("/{channel_id}/set-default", response_model=ChannelResponse)
async def set_default_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Mark a channel as the user's default."""
    channel = await _get_channel_or_404(channel_id, current_user.id, db)

    await _clear_default_flag(current_user.id, db)
    channel.is_default = True
    channel.updated_at = _utcnow()
    db.add(channel)
    await db.flush()

    logger.info("Default channel set: id=%s user=%s", channel.id, current_user.email)
    return _serialize_channel(channel)


# ── POST /channels/{channel_id}/link-youtube ─────────────────────────

@router.post("/{channel_id}/link-youtube", response_model=ChannelResponse)
@limiter.limit("10/hour")
async def link_youtube(
    request: Request,
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    """Link a channel to the user's existing YouTube OAuth connection.

    Copies the YouTube channel_id and oauth_token_id from the user's
    OAuthToken into this Channel row.
    """
    channel = await _get_channel_or_404(channel_id, current_user.id, db)

    # Fetch the user's Google OAuth token
    tok_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = tok_result.scalar_one_or_none()

    if not oauth_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No YouTube connection found. Connect your YouTube account first via Settings.",
        )

    # Check if another channel is already linked to this YouTube channel
    if oauth_token.channel_id:
        existing_result = await db.execute(
            select(Channel).where(
                Channel.user_id == current_user.id,
                Channel.youtube_channel_id == oauth_token.channel_id,
                Channel.id != channel.id,
            )
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This YouTube channel is already linked to another Tubevo channel.",
            )

    channel.youtube_channel_id = oauth_token.channel_id
    channel.oauth_token_id = oauth_token.id
    channel.updated_at = _utcnow()

    # Update name from YouTube if channel still has default name
    if channel.name in ("My Channel", "") and oauth_token.channel_title:
        channel.name = oauth_token.channel_title

    db.add(channel)
    await db.flush()

    logger.info(
        "Channel linked to YouTube: ch=%s yt=%s user=%s",
        channel.id, oauth_token.channel_id, current_user.email,
    )
    return _serialize_channel(channel, oauth_token)
