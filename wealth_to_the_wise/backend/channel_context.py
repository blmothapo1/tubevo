# filepath: backend/channel_context.py
"""
Shared FastAPI dependency for resolving the "active channel" for a request.

Used by any endpoint that needs channel context (videos, schedules,
analytics, etc.) — only when ``FF_MULTI_CHANNEL`` is enabled.

Resolution order
-----------------
1. Explicit ``?channel_id=<uuid>`` query parameter.
2. User's default channel (``is_default=True``).
3. ``None`` (legacy single-channel mode — no channel row yet).

When the feature flag is **off**, the dependency always returns ``None``
so callers can treat ``None`` as "single-channel / legacy mode".
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.feature_flags import FF_MULTI_CHANNEL, is_enabled_for_user
from backend.models import Channel, User

logger = logging.getLogger("tubevo.backend.channel_context")


async def get_active_channel(
    channel_id: Optional[str] = Query(None, alias="channel_id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Channel | None:
    """Resolve the active channel for this request.

    Returns ``None`` when multi-channel is disabled or user has no
    channels — callers must handle this gracefully (legacy path).
    """
    if not is_enabled_for_user(FF_MULTI_CHANNEL, current_user):
        return None

    if channel_id:
        # Explicit channel requested — validate ownership
        result = await db.execute(
            select(Channel).where(
                Channel.id == channel_id,
                Channel.user_id == current_user.id,
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Channel not found.",
            )
        return channel

    # Fall back to user's default channel
    result = await db.execute(
        select(Channel).where(
            Channel.user_id == current_user.id,
            Channel.is_default.is_(True),
        )
    )
    channel = result.scalar_one_or_none()

    # If no default set, try the oldest channel
    if not channel:
        result = await db.execute(
            select(Channel)
            .where(Channel.user_id == current_user.id)
            .order_by(Channel.created_at.asc())
            .limit(1)
        )
        channel = result.scalar_one_or_none()

    return channel  # may be None if user has no channels at all
