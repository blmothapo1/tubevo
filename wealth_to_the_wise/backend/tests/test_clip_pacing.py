"""
Tests for Clip Duration Variety (#6)

Covers:
  - ClipPacingConfig dataclass defaults and construction
  - distribute_clip_durations() — uniform, enabled, edge-cases
  - VisualProfile integration (per-plan pacing configs)
  - video_builder integration (both _prepare_background paths)
"""

import random
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# ── Make project root importable ──────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ══════════════════════════════════════════════════════════════════════
# 1.  ClipPacingConfig dataclass
# ══════════════════════════════════════════════════════════════════════

class TestClipPacingConfig(unittest.TestCase):
    """Verify ClipPacingConfig defaults and construction."""

    def test_defaults(self):
        from visual_effects import ClipPacingConfig
        cfg = ClipPacingConfig()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.min_sec, 2.5)
        self.assertEqual(cfg.max_sec, 7.0)

    def test_custom_values(self):
        from visual_effects import ClipPacingConfig
        cfg = ClipPacingConfig(enabled=True, min_sec=1.5, max_sec=10.0)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.min_sec, 1.5)
        self.assertEqual(cfg.max_sec, 10.0)

    def test_pacing_in_visual_profile(self):
        """clip_pacing field is present and typed correctly on VisualProfile."""
        from visual_effects import VisualProfile, ClipPacingConfig, get_visual_profile
        profile = get_visual_profile("pro")
        self.assertIsInstance(profile.clip_pacing, ClipPacingConfig)
        self.assertTrue(profile.clip_pacing.enabled)


# ══════════════════════════════════════════════════════════════════════
# 2.  distribute_clip_durations() — core algorithm
# ══════════════════════════════════════════════════════════════════════

class TestDistributeClipDurations(unittest.TestCase):
    """Tests for the duration-distribution helper."""

    def setUp(self):
        from visual_effects import ClipPacingConfig, distribute_clip_durations
        self.distribute = distribute_clip_durations
        self.pacing = ClipPacingConfig(enabled=True, min_sec=2.5, max_sec=7.0)

    # ── Disabled / None pacing → uniform ────────────────────────────

    def test_none_pacing_returns_uniform(self):
        result = self.distribute(4, 20.0, None)
        self.assertEqual(len(result), 4)
        for d in result:
            self.assertAlmostEqual(d, 5.0, places=5)

    def test_disabled_pacing_returns_uniform(self):
        from visual_effects import ClipPacingConfig
        off = ClipPacingConfig(enabled=False, min_sec=2.0, max_sec=8.0)
        result = self.distribute(5, 30.0, off)
        self.assertEqual(len(result), 5)
        for d in result:
            self.assertAlmostEqual(d, 6.0, places=5)

    # ── Edge cases ──────────────────────────────────────────────────

    def test_zero_clips(self):
        result = self.distribute(0, 10.0, self.pacing)
        self.assertEqual(result, [])

    def test_single_clip_gets_entire_budget(self):
        result = self.distribute(1, 15.0, self.pacing)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0], 15.0, places=5)

    # ── Enabled pacing — basic properties ───────────────────────────

    def test_sum_equals_budget(self):
        """Total of all clip durations must match the budget."""
        result = self.distribute(6, 30.0, self.pacing)
        self.assertAlmostEqual(sum(result), 30.0, places=1)

    def test_correct_clip_count(self):
        result = self.distribute(8, 40.0, self.pacing)
        self.assertEqual(len(result), 8)

    def test_durations_are_positive(self):
        result = self.distribute(5, 25.0, self.pacing)
        for d in result:
            self.assertGreater(d, 0)

    def test_not_all_identical(self):
        """With randomisation enabled, clips should NOT all be the same length."""
        results = []
        for _ in range(10):
            r = self.distribute(5, 25.0, self.pacing)
            results.append(tuple(round(x, 2) for x in r))
        # At least some runs should produce different distributions
        unique = set(results)
        self.assertGreater(len(unique), 1, "Expected randomised durations")

    def test_deterministic_with_seed(self):
        """Same RNG seed → same output."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        r1 = self.distribute(5, 25.0, self.pacing, rng=rng1)
        r2 = self.distribute(5, 25.0, self.pacing, rng=rng2)
        self.assertEqual(r1, r2)

    def test_different_seeds_different_output(self):
        rng1 = random.Random(42)
        rng2 = random.Random(99)
        r1 = self.distribute(5, 25.0, self.pacing, rng=rng1)
        r2 = self.distribute(5, 25.0, self.pacing, rng=rng2)
        self.assertNotEqual(r1, r2)

    # ── Wide range pacing ───────────────────────────────────────────

    def test_agency_wide_range(self):
        from visual_effects import ClipPacingConfig
        wide = ClipPacingConfig(enabled=True, min_sec=2.0, max_sec=8.0)
        result = self.distribute(6, 30.0, wide)
        self.assertAlmostEqual(sum(result), 30.0, places=1)
        self.assertEqual(len(result), 6)

    # ── Many clips ──────────────────────────────────────────────────

    def test_many_clips(self):
        result = self.distribute(20, 60.0, self.pacing)
        self.assertEqual(len(result), 20)
        self.assertAlmostEqual(sum(result), 60.0, places=1)

    # ── Small budget ────────────────────────────────────────────────

    def test_small_budget(self):
        """Budget smaller than n * min_sec still works (values scale down)."""
        from visual_effects import ClipPacingConfig
        tight = ClipPacingConfig(enabled=True, min_sec=3.0, max_sec=6.0)
        result = self.distribute(5, 8.0, tight)
        self.assertEqual(len(result), 5)
        self.assertAlmostEqual(sum(result), 8.0, places=1)


# ══════════════════════════════════════════════════════════════════════
# 3.  Per-plan profile pacing settings
# ══════════════════════════════════════════════════════════════════════

class TestPlanPacingProfiles(unittest.TestCase):
    """Verify each plan tier has the expected pacing settings."""

    def test_free_pacing_disabled(self):
        from visual_effects import get_visual_profile
        p = get_visual_profile("free")
        self.assertFalse(p.clip_pacing.enabled)

    def test_starter_pacing_enabled(self):
        from visual_effects import get_visual_profile
        p = get_visual_profile("starter")
        self.assertTrue(p.clip_pacing.enabled)
        self.assertGreaterEqual(p.clip_pacing.min_sec, 2.0)
        self.assertLessEqual(p.clip_pacing.max_sec, 7.0)

    def test_pro_pacing_enabled(self):
        from visual_effects import get_visual_profile
        p = get_visual_profile("pro")
        self.assertTrue(p.clip_pacing.enabled)
        self.assertGreaterEqual(p.clip_pacing.min_sec, 2.0)
        self.assertLessEqual(p.clip_pacing.max_sec, 8.0)

    def test_agency_pacing_widest(self):
        from visual_effects import get_visual_profile
        p = get_visual_profile("agency")
        self.assertTrue(p.clip_pacing.enabled)
        # Agency should have the widest range
        self.assertLessEqual(p.clip_pacing.min_sec, 2.5)
        self.assertGreaterEqual(p.clip_pacing.max_sec, 7.0)

    def test_agency_range_wider_than_starter(self):
        from visual_effects import get_visual_profile
        s = get_visual_profile("starter")
        a = get_visual_profile("agency")
        starter_range = s.clip_pacing.max_sec - s.clip_pacing.min_sec
        agency_range = a.clip_pacing.max_sec - a.clip_pacing.min_sec
        self.assertGreaterEqual(agency_range, starter_range)


# ══════════════════════════════════════════════════════════════════════
# 4.  video_builder integration — _prepare_background
# ══════════════════════════════════════════════════════════════════════

class TestPrepareBackgroundPacing(unittest.TestCase):
    """Verify _prepare_background uses distribute_clip_durations when pacing is enabled."""

    @patch("video_builder._run_ffmpeg")
    @patch("video_builder._get_video_duration")
    @patch("video_builder.shutil")
    def test_pacing_calls_distribute(self, mock_shutil, mock_dur, mock_ffmpeg):
        """When clip_pacing.enabled=True, distribute_clip_durations is called."""
        from visual_effects import get_visual_profile
        import video_builder
        import tempfile

        mock_dur.return_value = 10.0
        profile = get_visual_profile("pro")  # pacing enabled

        clips = [f"/tmp/clip_{i}.mp4" for i in range(4)]
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch("visual_effects.distribute_clip_durations") as mock_dist:
                mock_dist.return_value = [5.0, 5.0, 5.0, 5.0]  # 20s total
                video_builder._prepare_background(
                    clips, 20.0, tmp_dir, visual_profile=profile,
                )
                mock_dist.assert_called_once()
                call_args = mock_dist.call_args
                self.assertEqual(call_args[0][0], 4)  # n_clips
                self.assertAlmostEqual(call_args[0][1], 20.0)  # budget
        finally:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    @patch("video_builder._run_ffmpeg")
    @patch("video_builder._get_video_duration")
    @patch("video_builder.shutil")
    def test_no_pacing_for_free_tier(self, mock_shutil, mock_dur, mock_ffmpeg):
        """Free tier should NOT call distribute_clip_durations."""
        from visual_effects import get_visual_profile
        import video_builder
        import tempfile

        mock_dur.return_value = 10.0
        profile = get_visual_profile("free")  # pacing disabled

        clips = [f"/tmp/clip_{i}.mp4" for i in range(4)]
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch("visual_effects.distribute_clip_durations") as mock_dist:
                video_builder._prepare_background(
                    clips, 20.0, tmp_dir, visual_profile=profile,
                )
                mock_dist.assert_not_called()
        finally:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 5.  video_builder integration — _prepare_background_from_scenes
# ══════════════════════════════════════════════════════════════════════

class TestSceneAwarePacing(unittest.TestCase):
    """Verify _prepare_background_from_scenes uses pacing for clip allotment."""

    @patch("video_builder._run_ffmpeg")
    @patch("video_builder._get_video_duration")
    @patch("video_builder.shutil")
    def test_scene_pacing_calls_distribute(self, mock_shutil, mock_dur, mock_ffmpeg):
        """Pro-tier scene-aware build should invoke distribute_clip_durations."""
        from visual_effects import get_visual_profile
        import video_builder
        import tempfile

        mock_dur.return_value = 8.0
        profile = get_visual_profile("pro")

        scene_data = [
            {"label": "intro", "clips": ["/tmp/c1.mp4", "/tmp/c2.mp4"], "duration": 10},
            {"label": "body", "clips": ["/tmp/c3.mp4", "/tmp/c4.mp4"], "duration": 10},
        ]
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch("visual_effects.distribute_clip_durations") as mock_dist:
                mock_dist.return_value = [5.0, 5.0]
                video_builder._prepare_background_from_scenes(
                    scene_data, 20.0, tmp_dir, visual_profile=profile,
                )
                # Should be called once per scene (2 scenes)
                self.assertEqual(mock_dist.call_count, 2)
        finally:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    @patch("video_builder._run_ffmpeg")
    @patch("video_builder._get_video_duration")
    @patch("video_builder.shutil")
    def test_scene_no_pacing_free_tier(self, mock_shutil, mock_dur, mock_ffmpeg):
        """Free-tier scene-aware build should NOT invoke distribute."""
        from visual_effects import get_visual_profile
        import video_builder
        import tempfile

        mock_dur.return_value = 8.0
        profile = get_visual_profile("free")

        scene_data = [
            {"label": "intro", "clips": ["/tmp/c1.mp4", "/tmp/c2.mp4"], "duration": 10},
        ]
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch("visual_effects.distribute_clip_durations") as mock_dist:
                video_builder._prepare_background_from_scenes(
                    scene_data, 10.0, tmp_dir, visual_profile=profile,
                )
                mock_dist.assert_not_called()
        finally:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 6.  Algorithm stress tests
# ══════════════════════════════════════════════════════════════════════

class TestDistributeStress(unittest.TestCase):
    """Stress / boundary testing for the distribution algorithm."""

    def setUp(self):
        from visual_effects import ClipPacingConfig, distribute_clip_durations
        self.distribute = distribute_clip_durations
        self.pacing = ClipPacingConfig(enabled=True, min_sec=2.0, max_sec=8.0)

    def test_100_clips(self):
        result = self.distribute(100, 500.0, self.pacing)
        self.assertEqual(len(result), 100)
        self.assertAlmostEqual(sum(result), 500.0, places=0)

    def test_repeated_calls_vary(self):
        """Multiple calls should produce different distributions (randomised)."""
        runs = [tuple(round(x, 2) for x in self.distribute(5, 25.0, self.pacing))
                for _ in range(20)]
        unique = set(runs)
        self.assertGreater(len(unique), 1)

    def test_two_clips_sum_correct(self):
        result = self.distribute(2, 10.0, self.pacing)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(sum(result), 10.0, places=1)

    def test_budget_much_larger_than_max(self):
        """Budget >> n*max_sec — durations should still sum correctly."""
        from visual_effects import ClipPacingConfig
        pacing = ClipPacingConfig(enabled=True, min_sec=1.0, max_sec=3.0)
        result = self.distribute(3, 100.0, pacing)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(sum(result), 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
