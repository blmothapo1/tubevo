# filepath: backend/errors.py
"""
Centralised error capture for the admin Errors page.

Usage:
    from backend.errors import capture_error
    await capture_error(
        db, "pipeline",
        message="Script generation failed: rate limit",
        stack=traceback_str,
        user_id=user.id,
        video_id=record_id,
    )

Fire-and-forget inside existing sessions — never raises.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PlatformError

logger = logging.getLogger("tubevo.backend.errors")


async def capture_error(
    db: AsyncSession,
    error_type: str,
    *,
    message: str,
    stack: str | None = None,
    user_id: str | None = None,
    video_id: str | None = None,
) -> str | None:
    """Insert a PlatformError row.  Best-effort — never raises.

    Returns the error ID on success, None on failure.
    """
    try:
        err = PlatformError(
            type=error_type,
            message=message[:2000],
            stack=stack[:10_000] if stack else None,
            user_id=user_id,
            video_id=video_id,
        )
        db.add(err)
        # Let the caller's commit flush it
        return err.id
    except Exception:
        logger.warning("Failed to capture platform error (%s)", error_type, exc_info=True)
        return None
