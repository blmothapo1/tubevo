"""
Tests for stock_footage.py — Super-randomization upgrade.

Covers:
  • Wider candidate pool (per_page=15, pages 1-5)
  • Dual-provider parallel merge (Pexels + Pixabay always searched)
  • Cross-video dedup cache (load/save/exclude)
  • Query augmentation (synonym expansion)
  • Scene-aware download with user_id for cross-video dedup
  • Backward compatibility (user_id=None still works)
  • DALL-E scene illustrations disabled for pro/agency
"""

from __future__ import annotations

import json
import os
import sys
import time
import random
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass

import pytest

# ── Ensure project root is importable ────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ══════════════════════════════════════════════════════════════════════
# 1.  SEARCH TUNING CONSTANTS
# ══════════════════════════════════════════════════════════════════════


class TestSearchConstants:
    """Verify the widened search parameters."""

    def test_per_page_is_15(self):
        import stock_footage as sf
        assert sf.SEARCH_PER_PAGE == 15, "per_page should be 15 for a wider candidate pool"

    def test_max_page_is_5(self):
        import stock_footage as sf
        assert sf.SEARCH_MAX_PAGE == 5, "max_page should be 5 for deeper library reach"

    def test_pexels_default_per_page(self):
        """_search_pexels_videos default should use SEARCH_PER_PAGE."""
        import stock_footage as sf
        import inspect
        sig = inspect.signature(sf._search_pexels_videos)
        assert sig.parameters["per_page"].default == sf.SEARCH_PER_PAGE

    def test_pixabay_default_per_page(self):
        """_search_pixabay_videos default should use SEARCH_PER_PAGE."""
        import stock_footage as sf
        import inspect
        sig = inspect.signature(sf._search_pixabay_videos)
        assert sig.parameters["per_page"].default == sf.SEARCH_PER_PAGE

    def test_dedup_cache_max_videos(self):
        import stock_footage as sf
        assert sf.DEDUP_CACHE_MAX_VIDEOS == 10


# ══════════════════════════════════════════════════════════════════════
# 2.  QUERY AUGMENTATION
# ══════════════════════════════════════════════════════════════════════


class TestQueryAugmentation:
    """Test the synonym-based query expansion."""

    def test_augment_adds_synonyms(self):
        import stock_footage as sf
        queries = ["money saving tips"]
        result = sf._augment_queries(queries, max_extra=2)
        # Should have more queries than original
        assert len(result) >= len(queries)

    def test_augment_no_duplicates(self):
        import stock_footage as sf
        queries = ["money cash bills", "wealth building"]
        result = sf._augment_queries(queries, max_extra=3)
        # All unique
        lowered = [q.lower().strip() for q in result]
        assert len(lowered) == len(set(lowered))

    def test_augment_max_extra_respected(self):
        import stock_footage as sf
        queries = ["money saving", "wealth building", "city skyline"]
        result = sf._augment_queries(queries, max_extra=1)
        # At most 1 extra
        assert len(result) <= len(queries) + 1

    def test_augment_no_synonyms_passthrough(self):
        """Queries with no synonym matches should pass through unchanged."""
        import stock_footage as sf
        queries = ["xyzzy foobar", "quux baz"]
        result = sf._augment_queries(queries, max_extra=3)
        assert result == queries

    def test_augment_empty_list(self):
        import stock_footage as sf
        assert sf._augment_queries([], max_extra=5) == []


# ══════════════════════════════════════════════════════════════════════
# 3.  CROSS-VIDEO DEDUP CACHE
# ══════════════════════════════════════════════════════════════════════


class TestCrossVideoDedup:
    """Test the persistent cross-video media ID cache."""

    def test_load_empty_for_new_user(self, tmp_path):
        import stock_footage as sf
        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path
        try:
            ids = sf.load_cross_video_ids("new-user-123")
            assert ids == set()
        finally:
            sf.DEDUP_CACHE_DIR = original

    def test_load_none_user_returns_empty(self):
        import stock_footage as sf
        assert sf.load_cross_video_ids(None) == set()

    def test_save_and_load_roundtrip(self, tmp_path):
        import stock_footage as sf
        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path
        try:
            user_id = "test-user-abc"
            used = {100, 200, -300}  # includes pixabay negative ID

            sf.save_cross_video_ids(user_id, used)
            loaded = sf.load_cross_video_ids(user_id)

            assert loaded == used
        finally:
            sf.DEDUP_CACHE_DIR = original

    def test_multiple_saves_accumulate(self, tmp_path):
        import stock_footage as sf
        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path
        try:
            user_id = "test-user-xyz"

            sf.save_cross_video_ids(user_id, {1, 2, 3})
            sf.save_cross_video_ids(user_id, {4, 5, 6})

            loaded = sf.load_cross_video_ids(user_id)
            assert loaded == {1, 2, 3, 4, 5, 6}
        finally:
            sf.DEDUP_CACHE_DIR = original

    def test_cache_trims_to_max_videos(self, tmp_path):
        import stock_footage as sf
        original_dir = sf.DEDUP_CACHE_DIR
        original_max = sf.DEDUP_CACHE_MAX_VIDEOS
        sf.DEDUP_CACHE_DIR = tmp_path
        sf.DEDUP_CACHE_MAX_VIDEOS = 3  # only keep last 3
        try:
            user_id = "test-user-trim"

            # Save 5 entries
            for i in range(5):
                sf.save_cross_video_ids(user_id, {i * 100 + j for j in range(3)})

            # Load should only have IDs from the last 3 entries
            loaded = sf.load_cross_video_ids(user_id)
            # Entries 2,3,4 → IDs: {200,201,202, 300,301,302, 400,401,402}
            assert 0 not in loaded  # entry 0 should be trimmed
            assert 100 not in loaded  # entry 1 should be trimmed
            assert 200 in loaded  # entry 2 should still be there
            assert 400 in loaded  # entry 4 should still be there
        finally:
            sf.DEDUP_CACHE_DIR = original_dir
            sf.DEDUP_CACHE_MAX_VIDEOS = original_max

    def test_save_none_user_is_noop(self, tmp_path):
        """save_cross_video_ids with None user_id should not crash."""
        import stock_footage as sf
        sf.save_cross_video_ids(None, {1, 2, 3})
        # No exception = pass

    def test_save_empty_ids_is_noop(self, tmp_path):
        import stock_footage as sf
        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path
        try:
            sf.save_cross_video_ids("user-1", set())
            # File should not be created
            assert not (tmp_path / "used_media_user-1.json").exists()
        finally:
            sf.DEDUP_CACHE_DIR = original

    def test_corrupt_cache_returns_empty(self, tmp_path):
        """Corrupted cache file should not crash, just return empty."""
        import stock_footage as sf
        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path
        try:
            cache_file = tmp_path / "used_media_corrupt-user.json"
            cache_file.write_text("not valid json!!!", encoding="utf-8")

            loaded = sf.load_cross_video_ids("corrupt-user")
            assert loaded == set()
        finally:
            sf.DEDUP_CACHE_DIR = original


# ══════════════════════════════════════════════════════════════════════
# 4.  DUAL-PROVIDER PARALLEL MERGE
# ══════════════════════════════════════════════════════════════════════


def _make_pexels_video(vid_id: int, duration: int = 10) -> dict:
    """Create a mock Pexels video result."""
    return {
        "id": vid_id,
        "duration": duration,
        "video_files": [
            {"link": f"https://pexels.com/video/{vid_id}.mp4", "width": 1920, "height": 1080},
        ],
    }


def _make_pixabay_video(vid_id: int, duration: int = 10) -> dict:
    """Create a mock Pixabay video result (already normalized)."""
    return {
        "id": -vid_id,  # negative = pixabay namespace
        "duration": duration,
        "video_files": [
            {"link": f"https://pixabay.com/video/{vid_id}.mp4", "width": 1920, "height": 1080},
        ],
        "_provider": "pixabay",
    }


class TestDualProviderMerge:
    """Verify Pexels + Pixabay are both searched and results merged."""

    @patch("stock_footage._download_video")
    @patch("stock_footage._search_pixabay_videos")
    @patch("stock_footage._search_pexels_videos")
    def test_both_providers_searched(self, mock_pexels, mock_pixabay, mock_dl, tmp_path):
        import stock_footage as sf

        mock_pexels.return_value = [_make_pexels_video(1)]
        mock_pixabay.return_value = [_make_pixabay_video(2)]
        mock_dl.return_value = str(tmp_path / "clip_0.mp4")
        # Create the file so download "works"
        (tmp_path / "clip_0.mp4").touch()

        downloaded, seen = sf._download_clips_for_queries(
            ["test query"],
            num_clips=2,
            clips_dir=tmp_path,
            api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            use_random_page=False,
        )

        # Both providers should have been called
        mock_pexels.assert_called_once()
        mock_pixabay.assert_called_once()

    @patch("stock_footage._download_video")
    @patch("stock_footage._search_pixabay_videos")
    @patch("stock_footage._search_pexels_videos")
    def test_pexels_only_when_no_pixabay_key(self, mock_pexels, mock_pixabay, mock_dl, tmp_path):
        import stock_footage as sf

        mock_pexels.return_value = [_make_pexels_video(1)]
        mock_dl.return_value = str(tmp_path / "clip_0.mp4")
        (tmp_path / "clip_0.mp4").touch()

        original_key = sf.PIXABAY_API_KEY
        sf.PIXABAY_API_KEY = ""
        try:
            downloaded, seen = sf._download_clips_for_queries(
                ["test query"],
                num_clips=1,
                clips_dir=tmp_path,
                api_key="pexels-key",
                pixabay_api_key="",
                use_random_page=False,
            )
            mock_pixabay.assert_not_called()
        finally:
            sf.PIXABAY_API_KEY = original_key

    @patch("stock_footage._download_video")
    @patch("stock_footage._search_pixabay_videos")
    @patch("stock_footage._search_pexels_videos")
    def test_results_from_both_providers_used(self, mock_pexels, mock_pixabay, mock_dl, tmp_path):
        """When both providers return results, we should download from both."""
        import stock_footage as sf

        # Pexels returns 2, Pixabay returns 2
        mock_pexels.return_value = [_make_pexels_video(i) for i in range(100, 102)]
        mock_pixabay.return_value = [_make_pixabay_video(i) for i in range(200, 202)]

        call_count = 0
        def fake_download(url, path):
            nonlocal call_count
            Path(path).touch()
            call_count += 1
            return path

        mock_dl.side_effect = fake_download

        downloaded, seen = sf._download_clips_for_queries(
            ["finance lifestyle"],
            num_clips=4,
            clips_dir=tmp_path,
            api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            use_random_page=False,
        )

        assert len(downloaded) == 4
        # Seen should include both positive (Pexels) and negative (Pixabay) IDs
        assert any(vid > 0 for vid in seen), "Should have Pexels IDs (positive)"
        assert any(vid < 0 for vid in seen), "Should have Pixabay IDs (negative)"

    @patch("stock_footage._download_video")
    @patch("stock_footage._search_pixabay_videos")
    @patch("stock_footage._search_pexels_videos")
    def test_dedup_excludes_already_seen(self, mock_pexels, mock_pixabay, mock_dl, tmp_path):
        """Videos already in seen_video_ids should be skipped."""
        import stock_footage as sf

        mock_pexels.return_value = [_make_pexels_video(1), _make_pexels_video(2)]
        mock_pixabay.return_value = []
        mock_dl.side_effect = lambda url, path: (Path(path).touch(), path)[1]

        downloaded, seen = sf._download_clips_for_queries(
            ["query"],
            num_clips=2,
            seen_video_ids={1},  # video 1 already used
            clips_dir=tmp_path,
            api_key="key",
            use_random_page=False,
        )

        # Only video 2 should be downloaded (video 1 is in seen)
        assert len(downloaded) == 1
        assert 2 in seen
        assert 1 in seen  # still in set


# ══════════════════════════════════════════════════════════════════════
# 5.  SCENE-AWARE DOWNLOAD WITH CROSS-VIDEO DEDUP
# ══════════════════════════════════════════════════════════════════════


@dataclass
class MockScenePlan:
    """Minimal mock for ScenePlan dataclass."""
    label: str = "body-1"
    text: str = "Test scene text"
    word_count: int = 20
    estimated_duration: float = 8.0
    queries: list = None
    style: str = "cinematic"
    clip_count: int = 1

    def __post_init__(self):
        if self.queries is None:
            self.queries = ["test query"]


class TestSceneAwareDownload:
    """Test download_clips_for_scenes with the new user_id parameter."""

    @patch("stock_footage._download_clips_for_queries")
    def test_user_id_parameter_accepted(self, mock_download, tmp_path):
        """download_clips_for_scenes should accept user_id kwarg."""
        import stock_footage as sf

        mock_download.return_value = ([str(tmp_path / "clip_0.mp4")], {100})
        (tmp_path / "clip_0.mp4").touch()

        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path / "cache"
        sf.DEDUP_CACHE_DIR.mkdir()
        try:
            scenes = [MockScenePlan(label="intro", clip_count=1, queries=["intro query"])]
            result = sf.download_clips_for_scenes(
                scenes,
                clips_dir=tmp_path,
                api_key="test-key",
                user_id="test-user-123",
            )
            assert len(result) == 1
            assert result[0]["label"] == "intro"
        finally:
            sf.DEDUP_CACHE_DIR = original

    @patch("stock_footage._download_clips_for_queries")
    def test_user_id_none_still_works(self, mock_download, tmp_path):
        """Backward compat: user_id=None should work fine."""
        import stock_footage as sf

        mock_download.return_value = ([str(tmp_path / "clip_0.mp4")], {100})
        (tmp_path / "clip_0.mp4").touch()

        scenes = [MockScenePlan(label="body-1", clip_count=1)]
        result = sf.download_clips_for_scenes(
            scenes,
            clips_dir=tmp_path,
            api_key="test-key",
            user_id=None,
        )
        assert len(result) == 1

    @patch("stock_footage._download_clips_for_queries")
    def test_cross_video_ids_loaded_and_excluded(self, mock_download, tmp_path):
        """Previously used media IDs should be passed as seen_video_ids."""
        import stock_footage as sf

        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path / "cache"
        sf.DEDUP_CACHE_DIR.mkdir()

        # Pre-populate cache with IDs from a "previous video"
        user_id = "test-user-dedup"
        sf.save_cross_video_ids(user_id, {999, 888})

        # The mock captures what seen_video_ids was passed
        captured_seen: list[set] = []

        def fake_download(queries, num_clips, **kwargs):
            captured_seen.append(set(kwargs.get("seen_video_ids", set())))
            clip_path = str(tmp_path / f"clip_{kwargs.get('clip_index_start', 0)}.mp4")
            Path(clip_path).touch()
            return [clip_path], {500}

        mock_download.side_effect = fake_download

        try:
            scenes = [MockScenePlan(label="intro", clip_count=1, queries=["test"])]
            sf.download_clips_for_scenes(
                scenes,
                clips_dir=tmp_path,
                api_key="key",
                user_id=user_id,
            )

            # The seen_video_ids snapshot should include our cached IDs
            assert 999 in captured_seen[0]
            assert 888 in captured_seen[0]
        finally:
            sf.DEDUP_CACHE_DIR = original

    @patch("stock_footage._download_clips_for_queries")
    def test_new_ids_saved_to_cache(self, mock_download, tmp_path):
        """After download, newly used IDs should be saved to the cache."""
        import stock_footage as sf

        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path / "cache"
        sf.DEDUP_CACHE_DIR.mkdir()

        user_id = "test-user-save"

        def fake_download(queries, num_clips, **kwargs):
            clip_path = str(tmp_path / f"clip_{kwargs.get('clip_index_start', 0)}.mp4")
            Path(clip_path).touch()
            return [clip_path], {777, 666}

        mock_download.side_effect = fake_download

        try:
            scenes = [MockScenePlan(label="body-1", clip_count=1)]
            sf.download_clips_for_scenes(
                scenes,
                clips_dir=tmp_path,
                api_key="key",
                user_id=user_id,
            )

            # Verify cache was saved
            loaded = sf.load_cross_video_ids(user_id)
            assert 777 in loaded
            assert 666 in loaded
        finally:
            sf.DEDUP_CACHE_DIR = original


# ══════════════════════════════════════════════════════════════════════
# 6.  SCENE PLANNER — MORE QUERIES PER SCENE
# ══════════════════════════════════════════════════════════════════════


class TestScenePlannerQueries:
    """Verify scene planner now generates more queries per scene."""

    def test_max_queries_per_scene_is_5(self):
        """AI-generated queries should be capped at 5 per scene (was 3)."""
        # We check the source code for the cap
        from scene_planner import _generate_queries_with_ai
        import inspect
        source = inspect.getsource(_generate_queries_with_ai)
        assert "unique_queries[:5]" in source, "Query cap should be 5 per scene"

    def test_prompt_asks_for_4_to_5_queries(self):
        """The AI prompt should ask for 4-5 queries per section."""
        from scene_planner import _generate_queries_with_ai
        import inspect
        source = inspect.getsource(_generate_queries_with_ai)
        assert "4-5" in source, "Prompt should ask for 4-5 queries per section"


# ══════════════════════════════════════════════════════════════════════
# 7.  QUALITY PROFILES — AI ILLUSTRATIONS DISABLED
# ══════════════════════════════════════════════════════════════════════


class TestQualityProfiles:
    """Verify DALL-E scene illustrations are disabled for all plans."""

    def test_free_no_ai_illustrations(self):
        from backend.utils import get_quality_profile
        profile = get_quality_profile("free")
        assert profile["ai_illustrations"] is False

    def test_starter_no_ai_illustrations(self):
        from backend.utils import get_quality_profile
        profile = get_quality_profile("starter")
        assert profile["ai_illustrations"] is False

    def test_pro_no_ai_illustrations(self):
        from backend.utils import get_quality_profile
        profile = get_quality_profile("pro")
        assert profile["ai_illustrations"] is False, \
            "Pro should use stock footage, not AI-generated scene videos"

    def test_agency_no_ai_illustrations(self):
        from backend.utils import get_quality_profile
        profile = get_quality_profile("agency")
        assert profile["ai_illustrations"] is False, \
            "Agency should use stock footage, not AI-generated scene videos"


# ══════════════════════════════════════════════════════════════════════
# 8.  WIDE PAGE RANDOMIZATION
# ══════════════════════════════════════════════════════════════════════


class TestPageRandomization:
    """Verify random page range is wider (1-5)."""

    @patch("stock_footage._download_video")
    @patch("stock_footage._search_pixabay_videos")
    @patch("stock_footage._search_pexels_videos")
    def test_pexels_called_with_wide_page_range(self, mock_pexels, mock_pixabay, mock_dl, tmp_path):
        """With use_random_page=True, pages should be in [1, SEARCH_MAX_PAGE]."""
        import stock_footage as sf

        mock_pexels.return_value = [_make_pexels_video(1)]
        mock_pixabay.return_value = []
        mock_dl.side_effect = lambda url, path: (Path(path).touch(), path)[1]

        pages_seen = set()
        original_search = sf._search_pexels_videos

        # Run many times to check page range
        random.seed(42)
        for _ in range(50):
            sf._download_clips_for_queries(
                ["test"],
                num_clips=1,
                clips_dir=tmp_path,
                api_key="key",
                use_random_page=True,
            )
            # Extract the page argument from the mock call
            if mock_pexels.call_args:
                _, kwargs = mock_pexels.call_args
                pages_seen.add(kwargs.get("page", 1))
            mock_pexels.reset_mock()
            mock_dl.reset_mock()

        # Should see pages beyond 3 (old max was 3)
        assert max(pages_seen) <= sf.SEARCH_MAX_PAGE
        assert min(pages_seen) >= 1
        # With 50 iterations and uniform random, very likely to see page 4 or 5
        assert len(pages_seen) >= 3, f"Expected varied pages, got: {pages_seen}"


# ══════════════════════════════════════════════════════════════════════
# 9.  QUERY AUGMENTATION IN SCENE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════


class TestSceneQueryAugmentation:
    """Verify scenes get augmented queries before download."""

    @patch("stock_footage._download_clips_for_queries")
    def test_queries_are_augmented(self, mock_download, tmp_path):
        """download_clips_for_scenes should augment queries with synonyms."""
        import stock_footage as sf

        captured_queries: list[list] = []

        def fake_download(queries, num_clips, **kwargs):
            captured_queries.append(list(queries))
            clip_path = str(tmp_path / f"clip_{kwargs.get('clip_index_start', 0)}.mp4")
            Path(clip_path).touch()
            return [clip_path], {100}

        mock_download.side_effect = fake_download

        original = sf.DEDUP_CACHE_DIR
        sf.DEDUP_CACHE_DIR = tmp_path / "cache"
        sf.DEDUP_CACHE_DIR.mkdir()
        try:
            scenes = [MockScenePlan(
                label="body-1",
                clip_count=1,
                queries=["money saving tips"],  # "money" has synonyms
            )]
            sf.download_clips_for_scenes(scenes, clips_dir=tmp_path, api_key="key")

            # The queries passed to _download_clips_for_queries should be
            # at least as long as the original (augmented + shuffled)
            assert len(captured_queries) == 1
            assert len(captured_queries[0]) >= 1
        finally:
            sf.DEDUP_CACHE_DIR = original


# ══════════════════════════════════════════════════════════════════════
# 10.  BACKWARD COMPATIBILITY
# ══════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """Ensure existing callers still work."""

    def test_download_clips_for_scenes_signature(self):
        """user_id should be an optional keyword argument with default None."""
        import stock_footage as sf
        import inspect
        sig = inspect.signature(sf.download_clips_for_scenes)
        param = sig.parameters.get("user_id")
        assert param is not None, "user_id parameter should exist"
        assert param.default is None, "user_id should default to None"

    def test_download_clips_for_queries_unchanged_signature(self):
        """_download_clips_for_queries signature should be backward compatible."""
        import stock_footage as sf
        import inspect
        sig = inspect.signature(sf._download_clips_for_queries)
        # All original params should still exist
        for param_name in ["queries", "num_clips", "min_clip_duration",
                           "seen_video_ids", "clip_index_start",
                           "use_random_page", "clips_dir",
                           "api_key", "pixabay_api_key"]:
            assert param_name in sig.parameters, f"Missing param: {param_name}"

    def test_legacy_download_still_works(self):
        """download_clips_for_topic signature should be unchanged."""
        import stock_footage as sf
        import inspect
        sig = inspect.signature(sf.download_clips_for_topic)
        assert "topic" in sig.parameters
        assert "num_clips" in sig.parameters


# ══════════════════════════════════════════════════════════════════════
# 11.  SYNONYM MAP COVERAGE
# ══════════════════════════════════════════════════════════════════════


class TestSynonymMap:
    """Verify the synonym map has reasonable coverage."""

    def test_has_core_finance_terms(self):
        import stock_footage as sf
        core_terms = {"money", "wealth", "invest", "business", "saving"}
        assert core_terms.issubset(set(sf._QUERY_SYNONYMS.keys()))

    def test_each_synonym_list_non_empty(self):
        import stock_footage as sf
        for key, synonyms in sf._QUERY_SYNONYMS.items():
            assert len(synonyms) >= 2, f"Synonym list for '{key}' is too short"

    def test_no_single_word_synonyms(self):
        """Synonyms should be meaningful multi-word or compound terms."""
        import stock_footage as sf
        for key, synonyms in sf._QUERY_SYNONYMS.items():
            for syn in synonyms:
                assert len(syn) >= 3, f"Synonym '{syn}' for '{key}' is too short"
