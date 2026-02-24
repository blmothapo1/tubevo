# filepath: backend/tests/conftest.py
"""
Shared pytest fixtures / env-var bootstrapping for the backend test-suite.

This file is loaded automatically by pytest before any test module.
"""

from __future__ import annotations

import os

import pytest

# ── Ensure required env vars exist during tests ─────────────────────
# jwt_secret_key is a required pydantic field (no default).
# Set a deterministic test value so Settings() doesn't blow up at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the SlowAPI in-memory rate limit store between every test.

    Without this, rate limits accumulate across tests and cause
    spurious 429 failures.
    """
    from backend.rate_limit import limiter

    yield

    try:
        limiter.reset()
    except Exception:
        # limiter.reset() may not exist on older versions —
        # fall back to clearing the internal storage.
        if hasattr(limiter, "_storage"):
            limiter._storage.reset()
        elif hasattr(limiter, "_limiter"):
            storage = getattr(limiter._limiter, "_storage", None)
            if storage is not None:
                if hasattr(storage, "reset"):
                    storage.reset()
                elif hasattr(storage, "storage"):
                    storage.storage.clear()
