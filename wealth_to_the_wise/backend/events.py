# filepath: backend/events.py
"""
Lightweight event logger for the admin activity feed.

Usage:
    from backend.events import emit_event
    await emit_event(db, "user_signup", user_id=user.id, meta={"email": user.email})

Events are fire-and-forget inside existing request sessions — no extra
DB connections or background tasks needed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AdminEvent

logger = logging.getLogger("tubevo.backend.events")


async def emit_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: str | None = None,
    video_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Insert an admin event row.  Best-effort — never raises."""
    try:
        event = AdminEvent(
            type=event_type,
            user_id=user_id,
            video_id=video_id,
            metadata_json=json.dumps(meta) if meta else None,
        )
        db.add(event)
        # Don't flush here — let the request's commit handle it
    except Exception:
        logger.warning("Failed to emit admin event %s", event_type, exc_info=True)
