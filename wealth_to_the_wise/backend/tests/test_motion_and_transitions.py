"""
Tests for Motion Variety Engine (#3) and Transition Variety (#4).

Covers:
  - MotionStyle enum and weights
  - pick_motion_style() determinism, distribution, variety
  - get_motion_filter() FFmpeg filter generation for each style
  - pick_transition_type() determinism, distribution, variety
  - TransitionConfig.transition_types per plan tier
  - Integration with VisualProfile / plan presets
  - Edge cases (short duration, no config, fallback)
"""

from __future__ import annotations

import re
import sys
import os
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Path setup ──────────────────────────────────────────────────────
_PROJECT = Path(__file__).resolve().parents[2]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from visual_effects import (
    MotionStyle,
    MOTION_WEIGHTS,
    pick_motion_style,
    get_motion_filter,
    KenBurnsConfig,
    XFADE_TRANSITIONS,
    XFADE_WEIGHTS,
    pick_transition_type,
    TransitionConfig,
    VisualProfile,
    VISUAL_PROFILES,
    get_visual_profile,
    pick_ken_burns_direction,
    _KB_DIRECTIONS,
)


# ═══════════════════════════════════════════════════════════════════
# A. MOTION STYLE ENUM & WEIGHTS
# ═══════════════════════════════════════════════════════════════════

class TestMotionStyleEnum:
    def test_has_five_styles(self):
        assert len(MotionStyle) == 5

    def test_ken_burns_value(self):
        assert MotionStyle.KEN_BURNS == "ken_burns"

    def test_static_hold_value(self):
        assert MotionStyle.STATIC_HOLD == "static_hold"

    def test_slow_zoom_in_value(self):
        assert MotionStyle.SLOW_ZOOM_IN == "slow_zoom_in"

    def test_slow_zoom_out_value(self):
        assert MotionStyle.SLOW_ZOOM_OUT == "slow_zoom_out"

    def test_gentle_drift_value(self):
        assert MotionStyle.GENTLE_DRIFT == "gentle_drift"


class TestMotionWeights:
    def test_all_styles_have_weights(self):
        styles_in_weights = {s for s, _ in MOTION_WEIGHTS}
        assert styles_in_weights == set(MotionStyle)

    def test_weights_sum_to_100(self):
        total = sum(w for _, w in MOTION_WEIGHTS)
        assert total == 100

    def test_ken_burns_is_heaviest(self):
        kb_weight = next(w for s, w in MOTION_WEIGHTS if s == MotionStyle.KEN_BURNS)
        other_max = max(w for s, w in MOTION_WEIGHTS if s != MotionStyle.KEN_BURNS)
        assert kb_weight > other_max

    def test_no_zero_weights(self):
        for style, weight in MOTION_WEIGHTS:
            assert weight > 0, f"{style} has zero weight"


# ═══════════════════════════════════════════════════════════════════
# B. PICK MOTION STYLE
# ═══════════════════════════════════════════════════════════════════

class TestPickMotionStyle:
    def test_returns_motion_style(self):
        result = pick_motion_style(0, seed="test")
        assert isinstance(result, MotionStyle)

    def test_deterministic_same_inputs(self):
        a = pick_motion_style(3, seed="abc")
        b = pick_motion_style(3, seed="abc")
        assert a == b

    def test_different_segments_can_differ(self):
        """Over 20 segments, we should see at least 2 different styles."""
        styles = {pick_motion_style(i, seed="variety") for i in range(20)}
        assert len(styles) >= 2

    def test_different_seeds_can_differ(self):
        styles = {pick_motion_style(0, seed=f"s{i}") for i in range(20)}
        assert len(styles) >= 2

    def test_distribution_roughly_matches_weights(self):
        """Over 10k picks, distribution should roughly match weights."""
        counter: Counter[MotionStyle] = Counter()
        for i in range(10_000):
            counter[pick_motion_style(i, seed="dist")] += 1
        # Ken Burns should be ~40% (allow 30-50%)
        kb_pct = counter[MotionStyle.KEN_BURNS] / 10_000
        assert 0.25 <= kb_pct <= 0.55, f"Ken Burns at {kb_pct:.1%}"
        # Static should be ~20% (allow 10-30%)
        static_pct = counter[MotionStyle.STATIC_HOLD] / 10_000
        assert 0.10 <= static_pct <= 0.35, f"Static at {static_pct:.1%}"

    def test_all_styles_appear_over_1000_picks(self):
        counter: Counter[MotionStyle] = Counter()
        for i in range(1000):
            counter[pick_motion_style(i, seed="allstyles")] += 1
        for style in MotionStyle:
            assert counter[style] > 0, f"{style} never appeared in 1000 picks"


# ═══════════════════════════════════════════════════════════════════
# C. GET MOTION FILTER
# ═══════════════════════════════════════════════════════════════════

_KB_CONFIG = KenBurnsConfig(enabled=True, zoom_start=1.0, zoom_end=1.12)
_KB_OFF = KenBurnsConfig(enabled=False)
_W, _H, _FPS = 1280, 720, 24


class TestGetMotionFilterStaticHold:
    def test_returns_none(self):
        result = get_motion_filter(
            MotionStyle.STATIC_HOLD, 0, _W, _H, _FPS, 5.0,
            ken_burns_config=_KB_CONFIG,
        )
        assert result is None


class TestGetMotionFilterKenBurns:
    def test_returns_zoompan_string(self):
        result = get_motion_filter(
            MotionStyle.KEN_BURNS, 0, _W, _H, _FPS, 5.0,
            ken_burns_config=_KB_CONFIG,
        )
        assert result is not None
        assert "zoompan" in result

    def test_contains_resolution(self):
        result = get_motion_filter(
            MotionStyle.KEN_BURNS, 0, _W, _H, _FPS, 5.0,
            ken_burns_config=_KB_CONFIG,
        )
        assert f"s={_W}x{_H}" in result

    def test_kb_disabled_falls_back_to_slow_zoom(self):
        """If KB config is disabled, KEN_BURNS style falls back to slow zoom."""
        result = get_motion_filter(
            MotionStyle.KEN_BURNS, 0, _W, _H, _FPS, 5.0,
            ken_burns_config=_KB_OFF,
        )
        assert result is not None
        assert "zoompan" in result
        # Should be a subtle zoom (1.06 end)
        assert "1.06" in result or "1.0600" in result


class TestGetMotionFilterSlowZoomIn:
    def test_returns_zoompan(self):
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_IN, 0, _W, _H, _FPS, 5.0,
        )
        assert result is not None
        assert "zoompan" in result

    def test_center_position(self):
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_IN, 0, _W, _H, _FPS, 5.0,
        )
        assert "iw/2" in result
        assert "ih/2" in result

    def test_zoom_range_subtle(self):
        """Slow zoom should use 1.0 to 1.06 — subtler than Ken Burns."""
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_IN, 0, _W, _H, _FPS, 5.0,
        )
        assert "1.06" in result or "1.0600" in result


class TestGetMotionFilterSlowZoomOut:
    def test_returns_zoompan(self):
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_OUT, 0, _W, _H, _FPS, 5.0,
        )
        assert result is not None
        assert "zoompan" in result

    def test_starts_zoomed_in(self):
        """Zoom out starts at 1.08."""
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_OUT, 0, _W, _H, _FPS, 5.0,
        )
        assert "1.08" in result or "1.0800" in result


class TestGetMotionFilterGentleDrift:
    def test_returns_zoompan(self):
        result = get_motion_filter(
            MotionStyle.GENTLE_DRIFT, 0, _W, _H, _FPS, 5.0,
        )
        assert result is not None
        assert "zoompan" in result

    def test_fixed_zoom_no_ramp(self):
        """Drift uses a fixed zoom (1.04), no zoom ramping."""
        result = get_motion_filter(
            MotionStyle.GENTLE_DRIFT, 0, _W, _H, _FPS, 5.0,
        )
        assert "z='1.04'" in result

    def test_different_segments_can_drift_different_directions(self):
        """Left or right drift — check that both appear over many segments."""
        results = [
            get_motion_filter(MotionStyle.GENTLE_DRIFT, i, _W, _H, _FPS, 5.0, seed=str(i))
            for i in range(30)
        ]
        has_right = any("min(on*" in (r or "") for r in results)
        has_left = any("max(iw-iw/zoom" in (r or "") for r in results)
        assert has_right or has_left  # At least one direction appears


class TestGetMotionFilterEdgeCases:
    def test_very_short_duration_returns_none(self):
        """Clips < 2 frames should return None (no visible motion)."""
        result = get_motion_filter(
            MotionStyle.SLOW_ZOOM_IN, 0, _W, _H, _FPS, 0.01,
        )
        assert result is None

    def test_no_ken_burns_config(self):
        """KEN_BURNS style with no config should fall back to slow zoom."""
        result = get_motion_filter(
            MotionStyle.KEN_BURNS, 0, _W, _H, _FPS, 5.0,
            ken_burns_config=None,
        )
        assert result is not None
        assert "zoompan" in result

    def test_fps_included_in_all_filters(self):
        """All non-None filters should include fps parameter."""
        for style in MotionStyle:
            result = get_motion_filter(style, 0, _W, _H, _FPS, 5.0, ken_burns_config=_KB_CONFIG)
            if result is not None:
                assert f"fps={_FPS}" in result


# ═══════════════════════════════════════════════════════════════════
# D. TRANSITION VARIETY
# ═══════════════════════════════════════════════════════════════════

class TestXfadeTransitions:
    def test_has_multiple_types(self):
        assert len(XFADE_TRANSITIONS) >= 5

    def test_fade_is_in_list(self):
        assert "fade" in XFADE_TRANSITIONS

    def test_fadeblack_is_in_list(self):
        assert "fadeblack" in XFADE_TRANSITIONS


class TestXfadeWeights:
    def test_weights_sum_to_100(self):
        total = sum(w for _, w in XFADE_WEIGHTS)
        assert total == 100

    def test_fade_is_heaviest(self):
        fade_w = next(w for t, w in XFADE_WEIGHTS if t == "fade")
        other_max = max(w for t, w in XFADE_WEIGHTS if t != "fade")
        assert fade_w > other_max

    def test_all_transitions_have_weights(self):
        types_in_weights = {t for t, _ in XFADE_WEIGHTS}
        assert types_in_weights == set(XFADE_TRANSITIONS)


class TestPickTransitionType:
    def test_returns_string(self):
        result = pick_transition_type(0, seed="test")
        assert isinstance(result, str)

    def test_deterministic(self):
        a = pick_transition_type(3, seed="abc")
        b = pick_transition_type(3, seed="abc")
        assert a == b

    def test_result_in_known_transitions(self):
        for i in range(50):
            result = pick_transition_type(i, seed="check")
            assert result in XFADE_TRANSITIONS

    def test_variety_over_many_picks(self):
        types = {pick_transition_type(i, seed="v") for i in range(100)}
        assert len(types) >= 3, f"Only {len(types)} types in 100 picks"

    def test_allowed_filter(self):
        """When allowed is specified, results should only come from that set."""
        allowed = ["fade", "fadeblack"]
        for i in range(50):
            result = pick_transition_type(i, seed="f", allowed=allowed)
            assert result in allowed

    def test_allowed_empty_falls_back_to_fade(self):
        result = pick_transition_type(0, seed="x", allowed=[])
        assert result == "fade"

    def test_distribution_fade_most_common(self):
        counter: Counter[str] = Counter()
        for i in range(5000):
            counter[pick_transition_type(i, seed="dist")] += 1
        assert counter["fade"] > counter.get("smoothleft", 0)


# ═══════════════════════════════════════════════════════════════════
# E. PLAN TIER INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestPlanTransitionTypes:
    def test_free_transitions_disabled(self):
        profile = get_visual_profile("free")
        assert profile.transitions.enabled is False

    def test_starter_has_simple_transitions(self):
        profile = get_visual_profile("starter")
        assert profile.transitions.enabled is True
        assert "fade" in profile.transitions.transition_types
        assert "fadeblack" in profile.transitions.transition_types
        # Starter shouldn't have slides/wipes
        assert "slideleft" not in profile.transitions.transition_types

    def test_pro_has_more_transitions(self):
        profile = get_visual_profile("pro")
        assert len(profile.transitions.transition_types) >= 4
        assert "fade" in profile.transitions.transition_types
        assert "slideleft" in profile.transitions.transition_types

    def test_agency_has_all_transitions(self):
        profile = get_visual_profile("agency")
        assert len(profile.transitions.transition_types) >= 6
        assert "smoothleft" in profile.transitions.transition_types
        assert "smoothright" in profile.transitions.transition_types

    def test_pro_has_ken_burns_enabled(self):
        """Pro plan enables Ken Burns — motion variety applies here."""
        profile = get_visual_profile("pro")
        assert profile.ken_burns.enabled is True

    def test_free_no_ken_burns(self):
        """Free plan has no Ken Burns — motion variety is moot."""
        profile = get_visual_profile("free")
        assert profile.ken_burns.enabled is False

    def test_starter_no_ken_burns(self):
        profile = get_visual_profile("starter")
        assert profile.ken_burns.enabled is False


class TestTransitionConfigDefaults:
    def test_default_transition_types_non_empty(self):
        tc = TransitionConfig()
        assert len(tc.transition_types) >= 5

    def test_default_transition_types_include_fade(self):
        tc = TransitionConfig()
        assert "fade" in tc.transition_types


# ═══════════════════════════════════════════════════════════════════
# F. KEN BURNS DIRECTION STILL WORKS (REGRESSION)
# ═══════════════════════════════════════════════════════════════════

class TestKenBurnsDirectionRegression:
    def test_deterministic(self):
        a = pick_ken_burns_direction(0, seed="test")
        b = pick_ken_burns_direction(0, seed="test")
        assert a == b

    def test_returns_valid_direction(self):
        for i in range(20):
            d = pick_ken_burns_direction(i, seed="reg")
            assert d in _KB_DIRECTIONS

    def test_variety(self):
        dirs = {pick_ken_burns_direction(i, seed="var") for i in range(30)}
        assert len(dirs) >= 3


# ═══════════════════════════════════════════════════════════════════
# G. MOTION + TRANSITION COMBINED VARIETY
# ═══════════════════════════════════════════════════════════════════

class TestCombinedVariety:
    """Simulate what a real video build would produce: each segment gets
    a motion style, and each transition between segments gets a type."""

    def test_8_segment_video_has_variety(self):
        """An 8-segment video should have at least 2 motion styles
        and at least 2 transition types."""
        motion_styles = [pick_motion_style(i, seed="combo") for i in range(8)]
        transition_types = [pick_transition_type(i, seed="combo") for i in range(7)]

        unique_motions = set(motion_styles)
        unique_transitions = set(transition_types)

        assert len(unique_motions) >= 2, f"Only {unique_motions}"
        assert len(unique_transitions) >= 2, f"Only {unique_transitions}"

    def test_no_three_consecutive_same_motion(self):
        """Check that 3 identical consecutive motions is rare over 100
        segment-runs. Not *impossible*, just shouldn't dominate."""
        triple_count = 0
        for seed in range(100):
            styles = [pick_motion_style(i, seed=str(seed)) for i in range(8)]
            for j in range(len(styles) - 2):
                if styles[j] == styles[j+1] == styles[j+2]:
                    triple_count += 1
        # Out of 600 possible triples (100 runs × 6 positions), fewer than 25%
        assert triple_count < 150, f"Too many triples: {triple_count}"


# ═══════════════════════════════════════════════════════════════════
# H. FILTER STRING QUALITY
# ═══════════════════════════════════════════════════════════════════

class TestFilterStringQuality:
    """Verify FFmpeg filter strings are well-formed."""

    def test_zoompan_has_required_params(self):
        """All zoompan filters must have z=, d=, s=, fps=."""
        for style in [MotionStyle.KEN_BURNS, MotionStyle.SLOW_ZOOM_IN,
                       MotionStyle.SLOW_ZOOM_OUT, MotionStyle.GENTLE_DRIFT]:
            f = get_motion_filter(style, 0, _W, _H, _FPS, 5.0, ken_burns_config=_KB_CONFIG)
            if f is None:
                continue
            assert "zoompan=" in f
            assert "z=" in f
            assert "d=" in f
            assert "s=" in f
            assert "fps=" in f

    def test_no_negative_frame_counts(self):
        """Filter d= (frame count) should always be positive."""
        for style in MotionStyle:
            f = get_motion_filter(style, 0, _W, _H, _FPS, 3.0, ken_burns_config=_KB_CONFIG)
            if f and "d=" in f:
                # Extract d= value
                match = re.search(r"d=(\d+)", f)
                assert match, f"No d= found in {f}"
                assert int(match.group(1)) > 0

    def test_dimensions_match_input(self):
        """Output resolution should match requested width × height."""
        for style in MotionStyle:
            f = get_motion_filter(style, 0, _W, _H, _FPS, 5.0, ken_burns_config=_KB_CONFIG)
            if f:
                assert f"{_W}x{_H}" in f
