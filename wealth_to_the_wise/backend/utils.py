# filepath: backend/utils.py
"""
Shared utilities and constants for the backend package.

Provides safe wrappers around functions that live in the top-level
pipeline modules so that ``backend/`` code never needs a fragile
``sys.path`` hack or bare ``from config import …`` call.

Also contains canonical constants (like plan limits) so they live in
one place and every module can import from here without circular-dependency
risk.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ── Plan-based monthly video limits (single source of truth) ─────────
# Every module that needs these should ``from backend.utils import PLAN_MONTHLY_LIMITS``.
PLAN_MONTHLY_LIMITS: dict[str, int] = {
    "free": 1,
    "starter": 10,
    "pro": 50,
    "agency": 999_999,   # effectively unlimited
}

# ── Plan-based team seat limits (Phase 4) ────────────────────────────
PLAN_TEAM_SEAT_LIMITS: dict[str, int] = {
    "free": 0,         # no team feature
    "starter": 3,
    "pro": 10,
    "agency": 25,
}

# ── Plan-based max teams per user (Phase 4) ──────────────────────────
PLAN_MAX_TEAMS: dict[str, int] = {
    "free": 0,
    "starter": 1,
    "pro": 3,
    "agency": 10,
}


# ── API-key masking ──────────────────────────────────────────────────
# We try to import the canonical ``mask_secrets`` from the top-level
# ``config.py``.  If the import fails (e.g. in tests that don't have
# the project root on sys.path), we fall back to a lightweight local
# implementation so the error-handling path never crashes itself.

_mask_fn = None  # type: ignore[assignment]

try:
    _project_root = str(Path(__file__).resolve().parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from config import mask_secrets as _config_mask
    _mask_fn = _config_mask
except Exception:
    pass


# Lightweight fallback regex — covers the most common key prefixes.
_FALLBACK_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|sk-proj-[A-Za-z0-9_-]{10,}|xi-[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{30,})"
)


def mask_secrets(text: str) -> str:
    """Redact known API-key patterns from *text*.

    Delegates to the top-level ``config.mask_secrets`` if available,
    otherwise falls back to a simple regex substitution.
    """
    if not text:
        return text
    if _mask_fn is not None:
        return _mask_fn(text)

    def _redact(m: re.Match) -> str:
        v = m.group(0)
        return v[:6] + "***" if len(v) > 6 else v[:2] + "***"

    return _FALLBACK_PATTERN.sub(_redact, text)
