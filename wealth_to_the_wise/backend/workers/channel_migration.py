# filepath: backend/workers/channel_migration.py
"""
One-time startup task: create a default Channel row for every user who
has an OAuthToken but no Channel yet.

This bridges the gap between the legacy single-channel architecture and
the new multi-channel model.  It runs every server boot (idempotent —
skips users that already have channels).

Gated behind FF_MULTI_CHANNEL; if the flag is off the task is a no-op.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, func

from backend.database import async_session_factory
from backend.feature_flags import FF_MULTI_CHANNEL, is_globally_enabled
from backend.models import Channel, OAuthToken, _new_uuid, _utcnow

logger = logging.getLogger("tubevo.worker.channel_migration")


async def backfill_default_channels() -> int:
    """Create default ``Channel`` rows for users missing one.

    Returns the number of channels created.
    """
    if not is_globally_enabled(FF_MULTI_CHANNEL):
        logger.info("Channel backfill skipped — FF_MULTI_CHANNEL is off")
        return 0

    created = 0
    async with async_session_factory() as db:
        # Find OAuthToken rows whose user_id has NO channel yet.
        existing_channel_users = (
            select(Channel.user_id).distinct()
        ).subquery()

        stmt = (
            select(OAuthToken)
            .where(
                OAuthToken.user_id.notin_(
                    select(existing_channel_users.c.user_id)
                )
            )
        )
        result = await db.execute(stmt)
        tokens = result.scalars().all()

        for token in tokens:
            channel = Channel(
                id=_new_uuid(),
                user_id=token.user_id,
                name=token.channel_title or "My Channel",
                platform="youtube",
                youtube_channel_id=token.channel_id,
                oauth_token_id=token.id,
                is_default=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(channel)
            created += 1
            logger.info(
                "Created default channel for user=%s yt=%s",
                token.user_id,
                token.channel_id,
            )

        if created:
            await db.commit()

    logger.info("Channel backfill complete: %d channels created", created)
    return created
