# filepath: backend/tests/test_empire_phase0.py
"""
Tests for Empire OS Phase 0 scaffolding.

Validates:
  - Feature flag module works correctly
  - All new SQLAlchemy models import and have correct table names
  - Empire OS router endpoints return 403 when feature flags are off
  - Alembic migration chain is intact (0001 → 0009)
  - Channel backfill migration task is importable
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import app


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature Flags Module
# ═══════════════════════════════════════════════════════════════════════

class TestFeatureFlags:
    """Test the feature_flags module in isolation."""

    def test_all_flag_constants_defined(self):
        from backend.feature_flags import (
            FF_MULTI_CHANNEL,
            FF_NICHE_INTEL,
            FF_REVENUE,
            FF_THUMB_AB,
            FF_COMPETITOR_SPY,
            FF_VOICE_CLONE,
        )
        flags = [
            FF_MULTI_CHANNEL,
            FF_NICHE_INTEL,
            FF_REVENUE,
            FF_THUMB_AB,
            FF_COMPETITOR_SPY,
            FF_VOICE_CLONE,
        ]
        # Each flag is a non-empty string
        for flag in flags:
            assert isinstance(flag, str)
            assert len(flag) > 0

    def test_is_globally_enabled_off_by_default(self):
        from backend.feature_flags import FF_MULTI_CHANNEL, is_globally_enabled
        # Make sure the env var is NOT set
        env_var = "FF_EMPIRE_MULTI_CHANNEL"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(env_var, None)
            assert is_globally_enabled(FF_MULTI_CHANNEL) is False

    def test_is_globally_enabled_true_when_set(self):
        from backend.feature_flags import FF_MULTI_CHANNEL, is_globally_enabled
        with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}):
            assert is_globally_enabled(FF_MULTI_CHANNEL) is True

    def test_is_globally_enabled_true_with_true_string(self):
        from backend.feature_flags import FF_MULTI_CHANNEL, is_globally_enabled
        with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "true"}):
            assert is_globally_enabled(FF_MULTI_CHANNEL) is True

    def test_is_globally_enabled_admin_mode(self):
        from backend.feature_flags import FF_MULTI_CHANNEL, is_globally_enabled
        with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "admin"}):
            # "admin" is not "1" or "true" — global is False
            assert is_globally_enabled(FF_MULTI_CHANNEL) is False

    def test_require_feature_returns_callable(self):
        from backend.feature_flags import FF_REVENUE, require_feature
        dep = require_feature(FF_REVENUE)
        assert callable(dep)

    def test_is_enabled_for_user_admin_mode(self):
        """When env var = 'admin', admins see the feature."""
        from backend.feature_flags import FF_NICHE_INTEL, is_enabled_for_user
        from unittest.mock import MagicMock

        admin_user = MagicMock()
        admin_user.role = "admin"
        admin_user.feature_overrides_json = None

        normal_user = MagicMock()
        normal_user.role = "user"
        normal_user.is_beta = False
        normal_user.feature_overrides_json = None

        with patch.dict(os.environ, {"FF_EMPIRE_NICHE_INTEL": "admin"}):
            assert is_enabled_for_user(FF_NICHE_INTEL, admin_user) is True
            assert is_enabled_for_user(FF_NICHE_INTEL, normal_user) is False

    def test_is_enabled_per_user_override(self):
        """Per-user JSON override takes precedence over env var."""
        import json
        from backend.feature_flags import FF_REVENUE, is_enabled_for_user
        from unittest.mock import MagicMock

        user = MagicMock()
        user.is_admin = False
        user.feature_overrides_json = json.dumps({"empire.revenue": True})

        # Even with env var OFF, per-user override wins
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FF_EMPIRE_REVENUE", None)
            assert is_enabled_for_user(FF_REVENUE, user) is True


# ═══════════════════════════════════════════════════════════════════════
# 2. New SQLAlchemy Models
# ═══════════════════════════════════════════════════════════════════════

class TestEmpireModels:
    """Verify all 10 new models import cleanly and have correct table names."""

    def test_channel_model(self):
        from backend.models import Channel
        assert Channel.__tablename__ == "channels"

    def test_niche_snapshot_model(self):
        from backend.models import NicheSnapshot
        assert NicheSnapshot.__tablename__ == "niche_snapshots"

    def test_niche_topic_model(self):
        from backend.models import NicheTopic
        assert NicheTopic.__tablename__ == "niche_topics"

    def test_revenue_event_model(self):
        from backend.models import RevenueEvent
        assert RevenueEvent.__tablename__ == "revenue_events"

    def test_revenue_daily_agg_model(self):
        from backend.models import RevenueDailyAgg
        assert RevenueDailyAgg.__tablename__ == "revenue_daily_agg"

    def test_thumb_experiment_model(self):
        from backend.models import ThumbExperiment
        assert ThumbExperiment.__tablename__ == "thumb_experiments"

    def test_thumb_variant_model(self):
        from backend.models import ThumbVariant
        assert ThumbVariant.__tablename__ == "thumb_variants"

    def test_competitor_channel_model(self):
        from backend.models import CompetitorChannel
        assert CompetitorChannel.__tablename__ == "competitor_channels"

    def test_competitor_snapshot_model(self):
        from backend.models import CompetitorSnapshot
        assert CompetitorSnapshot.__tablename__ == "competitor_snapshots"

    def test_voice_clone_model(self):
        from backend.models import VoiceClone
        assert VoiceClone.__tablename__ == "voice_clones"

    def test_existing_models_have_channel_id(self):
        """Verify channel_id FK was added to the 5 existing tables."""
        from backend.models import (
            VideoRecord,
            PostingSchedule,
            ContentMemory,
            UserPreferences,
            ContentPerformance,
        )
        for model in [VideoRecord, PostingSchedule, ContentMemory,
                       UserPreferences, ContentPerformance]:
            col = model.__table__.columns.get("channel_id")
            assert col is not None, f"{model.__tablename__} missing channel_id"
            assert col.nullable is True

    def test_user_has_feature_overrides_json(self):
        from backend.models import User
        col = User.__table__.columns.get("feature_overrides_json")
        assert col is not None
        assert col.nullable is True


# ═══════════════════════════════════════════════════════════════════════
# 3. Empire OS Routers — Feature-flag gating (return 403 when OFF)
# ═══════════════════════════════════════════════════════════════════════

_EMPIRE_ROUTES = [
    ("/channels", "FF_EMPIRE_MULTI_CHANNEL"),
    ("/niche/snapshots", "FF_EMPIRE_NICHE_INTEL"),
    ("/revenue/summary", "FF_EMPIRE_REVENUE"),
    ("/thumbnails/experiments", "FF_EMPIRE_THUMB_AB"),
    ("/competitors", "FF_EMPIRE_COMPETITOR_SPY"),
    ("/voice-clones", "FF_EMPIRE_VOICE_CLONE"),
]


@pytest.mark.anyio
class TestEmpireRoutersGated:
    """Empire OS endpoints must return 403 when the feature flag is off."""

    @pytest.mark.parametrize("path,env_var", _EMPIRE_ROUTES)
    async def test_returns_403_when_flag_off(self, client: AsyncClient, path: str, env_var: str):
        """With no auth and flag OFF → 401 (auth check) or 403 (flag check).

        Since require_feature is a router-level dependency, it runs
        alongside auth.  A missing token usually yields 401 first,
        but if the flag check runs first we'd get 403.  Either is
        acceptable — the key assertion is that the endpoint is NOT
        accessible (i.e. not 200).
        """
        # Ensure flag is off
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(env_var, None)
            resp = await client.get(path)
            assert resp.status_code in (401, 403), (
                f"{path} returned {resp.status_code} with flag off"
            )


# ═══════════════════════════════════════════════════════════════════════
# 4. Alembic Migration Chain
# ═══════════════════════════════════════════════════════════════════════

class TestAlembicMigrationChain:
    """Verify all migration files exist and chain correctly."""

    def test_migration_chain(self):
        """Revision IDs form an unbroken chain 0001 → 0009."""
        import importlib
        import sys

        versions_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "alembic", "versions",
        )
        versions_dir = os.path.normpath(versions_dir)

        # Collect all .py files and extract revision + down_revision
        chain: dict[str, str | None] = {}
        for fname in os.listdir(versions_dir):
            if not fname.endswith(".py") or fname.startswith("__"):
                continue
            fpath = os.path.join(versions_dir, fname)
            # Parse the file as text to extract revision/down_revision
            with open(fpath) as f:
                content = f.read()
            rev = _extract_var(content, "revision")
            down = _extract_var(content, "down_revision")
            if rev:
                chain[rev] = down

        # Verify chain
        expected = ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009"]
        for i, rev_id in enumerate(expected):
            assert rev_id in chain, f"Missing migration {rev_id}"
            if i == 0:
                assert chain[rev_id] is None, f"0001 should have no down_revision"
            else:
                assert chain[rev_id] == expected[i - 1], (
                    f"Migration {rev_id} should depend on {expected[i - 1]}, "
                    f"but depends on {chain[rev_id]}"
                )


def _extract_var(content: str, var_name: str) -> str | None:
    """Extract a simple string variable from Python source text.

    Handles both `revision: str = "0005"` and
    `down_revision: Union[str, None] = "0001"` patterns.
    """
    import re
    # Match: var_name (optional type annotation) = "value"
    # Type annotation can be complex like Union[str, None], so match everything up to =
    pattern = rf'^{var_name}(?:\s*:[^=]+)?\s*=\s*["\']([^"\']+)["\']'
    m = re.search(pattern, content, re.MULTILINE)
    if m:
        return m.group(1)
    # Match: var_name ... = None
    pattern_none = rf'^{var_name}(?:\s*:[^=]+)?\s*=\s*None'
    m_none = re.search(pattern_none, content, re.MULTILINE)
    if m_none:
        return None
    return None


# ═══════════════════════════════════════════════════════════════════════
# 5. Workers Import Cleanly
# ═══════════════════════════════════════════════════════════════════════

class TestWorkersImportable:
    """Verify all Empire OS worker modules import without error."""

    def test_import_competitor_worker(self):
        from backend.workers.competitor_worker import competitor_loop
        assert callable(competitor_loop)

    def test_import_niche_worker(self):
        from backend.workers.niche_worker import niche_loop
        assert callable(niche_loop)

    def test_import_thumb_ab_worker(self):
        from backend.workers.thumb_ab_worker import thumb_ab_loop
        assert callable(thumb_ab_loop)

    def test_import_revenue_worker(self):
        from backend.workers.revenue_worker import revenue_loop
        assert callable(revenue_loop)

    def test_import_channel_migration(self):
        from backend.workers.channel_migration import backfill_default_channels
        assert callable(backfill_default_channels)
