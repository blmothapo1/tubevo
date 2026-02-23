# filepath: backend/tests/conftest.py
"""
Shared pytest fixtures / env-var bootstrapping for the backend test-suite.

This file is loaded automatically by pytest before any test module.
"""

from __future__ import annotations

import os

# ── Ensure required env vars exist during tests ─────────────────────
# jwt_secret_key is a required pydantic field (no default).
# Set a deterministic test value so Settings() doesn't blow up at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
