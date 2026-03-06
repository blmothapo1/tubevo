# filepath: backend/feature_flags.py
"""
Centralised feature flag system for Empire OS features.

Flags are controlled via:
1. Environment variables (global kill-switch)
2. Per-user overrides stored in ``users.feature_overrides_json``

Usage in routers::

    from backend.feature_flags import require_feature, FF_MULTI_CHANNEL

    @router.get("/channels", dependencies=[Depends(require_feature(FF_MULTI_CHANNEL))])
    async def list_channels(...): ...

Usage in workers::

    from backend.feature_flags import is_globally_enabled, FF_COMPETITOR_SPY

    if not is_globally_enabled(FF_COMPETITOR_SPY):
        return  # skip this cycle
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Depends, HTTPException, status

from backend.auth import get_current_user
from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.feature_flags")

# ── Flag names (constants) ───────────────────────────────────────────

FF_MULTI_CHANNEL = "empire.multi_channel"
FF_NICHE_INTEL = "empire.niche_intel"
FF_REVENUE = "empire.revenue"
FF_THUMB_AB = "empire.thumb_ab"
FF_COMPETITOR_SPY = "empire.competitor_spy"
FF_VOICE_CLONE = "empire.voice_clone"
FF_TREND_RADAR = "empire.trend_radar"

ALL_FLAGS = frozenset({
    FF_MULTI_CHANNEL,
    FF_NICHE_INTEL,
    FF_REVENUE,
    FF_THUMB_AB,
    FF_COMPETITOR_SPY,
    FF_VOICE_CLONE,
    FF_TREND_RADAR,
})

# ── Environment variable mapping ─────────────────────────────────────
# Each flag maps to an env var: empire.multi_channel → FF_EMPIRE_MULTI_CHANNEL
# Value "1" or "true" (case-insensitive) = enabled globally.
# Default = disabled (safe).

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_key(flag: str) -> str:
    """Convert a flag name to the expected env var name.

    ``empire.multi_channel`` → ``FF_EMPIRE_MULTI_CHANNEL``
    """
    return "FF_" + flag.upper().replace(".", "_")


def is_globally_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled at the environment level.

    This is the global kill-switch.  If the env var is not set or is
    falsy, the feature is off for everyone.
    """
    import os
    val = os.environ.get(_env_key(flag), "").strip().lower()
    return val in _TRUTHY


def is_enabled_for_user(flag: str, user: Any) -> bool:
    """Check if a feature is enabled for a specific user.

    Resolution order:
    1. Per-user override (``user.feature_overrides_json``) — if present, wins.
    2. Admin users (``user.role == 'admin'``) — all flags enabled when
       the global env var is set to ``"admin"`` or ``"1"``/``"true"``.
    3. Beta users (``user.is_beta``) — enabled when global env var is
       ``"beta"`` or ``"1"``/``"true"``.
    4. Global env var ``"1"``/``"true"`` — enabled for everyone.
    5. Default: disabled.
    """
    import os

    # 1. Per-user override
    overrides_raw = getattr(user, "feature_overrides_json", None)
    if overrides_raw:
        try:
            overrides = json.loads(overrides_raw)
            if flag in overrides:
                return bool(overrides[flag])
        except (json.JSONDecodeError, TypeError):
            pass

    # 2-5. Global env var with role awareness
    val = os.environ.get(_env_key(flag), "").strip().lower()

    if val in _TRUTHY:
        return True  # enabled for everyone

    if val == "admin" and getattr(user, "role", "") == "admin":
        return True

    if val == "beta" and getattr(user, "is_beta", False):
        return True

    return False


def require_feature(flag: str):
    """FastAPI dependency that gates an endpoint behind a feature flag.

    Returns HTTP 403 with a clear message when the feature is disabled.

    Usage::

        @router.get("/foo", dependencies=[Depends(require_feature(FF_MULTI_CHANNEL))])
        async def foo(): ...
    """
    from backend.models import User  # deferred to avoid circular import

    async def _check(current_user: User = Depends(get_current_user)):
        if not is_enabled_for_user(flag, current_user):
            logger.info(
                "Feature %s blocked for user %s (role=%s, beta=%s)",
                flag, current_user.email,
                getattr(current_user, "role", "?"),
                getattr(current_user, "is_beta", False),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature is not yet available for your account. (flag={flag})",
            )

    return _check
