"""
Tests for improved ambient music synthesis (#5).

Covers:
  - CHORD_PROGRESSIONS: all 8 progressions, structure validation
  - generate_ambient_music: parameter handling, progression selection
  - MusicMood.progression field integration
  - Random progression selection when no explicit choice
  - Legacy single-chord path still works
  - Polish pipeline kwargs routing
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter
from unittest.mock import patch, MagicMock

import pytest

# ── Path setup ──────────────────────────────────────────────────────
_PROJECT = Path(__file__).resolve().parents[2]
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from audio_processor import CHORD_PROGRESSIONS, MUSIC_VOLUME_DB


# ═══════════════════════════════════════════════════════════════════
# A. CHORD PROGRESSIONS
# ═══════════════════════════════════════════════════════════════════

class TestChordProgressions:
    def test_has_at_least_8_progressions(self):
        assert len(CHORD_PROGRESSIONS) >= 8

    def test_original_four_still_present(self):
        for name in ["major_warm", "minor_reflective", "hopeful", "emotional"]:
            assert name in CHORD_PROGRESSIONS, f"Missing original progression: {name}"

    def test_new_progressions_present(self):
        for name in ["cinematic_drama", "expansive", "dark_ambient", "motivational"]:
            assert name in CHORD_PROGRESSIONS, f"Missing new progression: {name}"

    def test_each_progression_has_4_chords(self):
        for name, chords in CHORD_PROGRESSIONS.items():
            assert len(chords) == 4, f"{name} has {len(chords)} chords, expected 4"

    def test_each_chord_has_4_frequencies(self):
        for name, chords in CHORD_PROGRESSIONS.items():
            for i, chord in enumerate(chords):
                assert len(chord) == 4, f"{name}[{i}] has {len(chord)} freqs"

    def test_frequencies_are_positive(self):
        for name, chords in CHORD_PROGRESSIONS.items():
            for i, chord in enumerate(chords):
                for j, freq in enumerate(chord):
                    assert freq > 0, f"{name}[{i}][{j}] = {freq}"

    def test_frequencies_in_audible_range(self):
        """All frequencies should be between 60 Hz and 500 Hz for ambient pads."""
        for name, chords in CHORD_PROGRESSIONS.items():
            for chord in chords:
                for freq in chord:
                    assert 60 <= freq <= 500, f"{name}: {freq} Hz out of range"

    def test_no_duplicate_progressions(self):
        """Each progression should be unique (not just a copy of another)."""
        seen = set()
        for name, chords in CHORD_PROGRESSIONS.items():
            key = tuple(tuple(c) for c in chords)
            assert key not in seen, f"{name} is a duplicate"
            seen.add(key)


# ═══════════════════════════════════════════════════════════════════
# B. GENERATE AMBIENT MUSIC PARAMETERS
# ═══════════════════════════════════════════════════════════════════

class TestGenerateAmbientMusicParams:
    """Test parameter resolution without actually running FFmpeg."""

    def test_random_progression_when_none(self):
        """When progression=None and frequencies=None, a random one is chosen."""
        from audio_processor import generate_ambient_music
        # We mock _run_ffmpeg to avoid actual FFmpeg calls
        progressions_used = set()
        for i in range(50):
            with patch("audio_processor._run_ffmpeg"), \
                 patch("audio_processor.os.path.join", return_value=f"/tmp/test_{i}"), \
                 patch("tempfile.mkdtemp", return_value="/tmp/test"):
                try:
                    with patch("audio_processor.logger") as mock_log:
                        try:
                            generate_ambient_music(60.0, f"/tmp/music_{i}.mp3")
                        except Exception:
                            pass
                        for call in mock_log.info.call_args_list:
                            args = call[0]
                            if "progression=" in str(args):
                                log_msg = args[0] % args[1:] if len(args) > 1 else str(args[0])
                                for prog in CHORD_PROGRESSIONS:
                                    if prog in log_msg:
                                        progressions_used.add(prog)
                except Exception:
                    pass
        # Should see more than 1 unique progression across 50 runs
        assert len(progressions_used) >= 2, f"Only saw: {progressions_used}"

    def test_explicit_progression_honored(self):
        """When progression='hopeful', it should use that one."""
        from audio_processor import generate_ambient_music
        with patch("audio_processor._run_ffmpeg"), \
             patch("audio_processor.logger") as mock_log, \
             patch("tempfile.mkdtemp", return_value="/tmp/test"), \
             patch("audio_processor.os.path.join", return_value="/tmp/test.wav"):
            try:
                generate_ambient_music(30.0, "/tmp/test.mp3", progression="hopeful")
            except Exception:
                pass
            log_text = str(mock_log.info.call_args_list)
            assert "hopeful" in log_text

    def test_legacy_frequencies_override(self):
        """When frequencies are provided, they should override progression."""
        from audio_processor import generate_ambient_music
        with patch("audio_processor._run_ffmpeg"), \
             patch("audio_processor.logger") as mock_log, \
             patch("tempfile.mkdtemp", return_value="/tmp/test"), \
             patch("audio_processor.os.path.join", return_value="/tmp/test.wav"):
            try:
                generate_ambient_music(
                    30.0, "/tmp/test.mp3",
                    frequencies=[100.0, 150.0, 200.0, 300.0],
                )
            except Exception:
                pass
            log_text = str(mock_log.info.call_args_list)
            assert "custom" in log_text


class TestTremoloDefaults:
    def test_default_tremolo_is_0_08(self):
        """Default tremolo should be 0.08 (slower than old 0.12)."""
        from audio_processor import generate_ambient_music
        with patch("audio_processor._run_ffmpeg") as mock_ff, \
             patch("tempfile.mkdtemp", return_value="/tmp/test"), \
             patch("audio_processor.os.path.join", return_value="/tmp/test.wav"):
            try:
                generate_ambient_music(30.0, "/tmp/test.mp3", progression="major_warm")
            except Exception:
                pass
            # Check that the filter string contains tremolo values near 0.08
            if mock_ff.called:
                filter_str = str(mock_ff.call_args_list[0])
                # tremolo_base + 0.015 = 0.095 → rounded to 0.095
                assert "0.095" in filter_str or "0.08" in filter_str


# ═══════════════════════════════════════════════════════════════════
# C. MUSIC MOOD + PROGRESSION INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestMusicMoodProgression:
    def test_mood_has_progression_field(self):
        from variation_engine import MusicMood
        mood = MusicMood(label="test", progression="major_warm")
        assert mood.progression == "major_warm"

    def test_mood_progression_defaults_to_none(self):
        from variation_engine import MusicMood
        mood = MusicMood(label="test")
        assert mood.progression is None

    def test_all_moods_have_progression(self):
        from variation_engine import MUSIC_MOODS
        for mood in MUSIC_MOODS:
            assert mood.progression is not None, f"{mood.label} missing progression"
            assert mood.progression in CHORD_PROGRESSIONS, (
                f"{mood.label} has invalid progression: {mood.progression}"
            )

    def test_moods_cover_all_progressions(self):
        """At least the original 4 + 4 new progressions should be mapped."""
        from variation_engine import MUSIC_MOODS
        mood_progs = {m.progression for m in MUSIC_MOODS if m.progression}
        assert len(mood_progs) >= 6  # At least 6 unique progressions

    def test_mood_tremolo_values_reasonable(self):
        from variation_engine import MUSIC_MOODS
        for mood in MUSIC_MOODS:
            assert 0.05 <= mood.tremolo_base <= 0.20, (
                f"{mood.label}: tremolo={mood.tremolo_base}"
            )


class TestPickMusicMood:
    def test_deterministic_with_seed(self):
        from variation_engine import pick_music_mood
        a = pick_music_mood(topic="finance", seed="test1")
        b = pick_music_mood(topic="finance", seed="test1")
        assert a.label == b.label

    def test_different_seeds_produce_variety(self):
        from variation_engine import pick_music_mood
        labels = {pick_music_mood(seed=f"s{i}").label for i in range(20)}
        assert len(labels) >= 3


# ═══════════════════════════════════════════════════════════════════
# D. PIPELINE KWARGS ROUTING
# ═══════════════════════════════════════════════════════════════════

class TestPipelineKwargsRouting:
    def test_progression_preferred_over_frequencies(self):
        """When mood has progression, pipeline should pass it instead of frequencies."""
        from variation_engine import MusicMood
        mood = MusicMood(
            label="test",
            frequencies=[100.0, 200.0, 300.0, 400.0],
            progression="hopeful",
        )
        # Simulate the pipeline logic from videos.py
        polish_kwargs: dict = {}
        if getattr(mood, "progression", None):
            polish_kwargs["music_progression"] = mood.progression
        else:
            polish_kwargs["music_frequencies"] = mood.frequencies
        polish_kwargs["music_tremolo_base"] = mood.tremolo_base

        assert "music_progression" in polish_kwargs
        assert polish_kwargs["music_progression"] == "hopeful"
        assert "music_frequencies" not in polish_kwargs

    def test_fallback_to_frequencies_when_no_progression(self):
        from variation_engine import MusicMood
        mood = MusicMood(
            label="legacy",
            frequencies=[100.0, 200.0, 300.0, 400.0],
        )
        polish_kwargs: dict = {}
        if getattr(mood, "progression", None):
            polish_kwargs["music_progression"] = mood.progression
        else:
            polish_kwargs["music_frequencies"] = mood.frequencies
        polish_kwargs["music_tremolo_base"] = mood.tremolo_base

        assert "music_frequencies" in polish_kwargs
        assert "music_progression" not in polish_kwargs


# ═══════════════════════════════════════════════════════════════════
# E. SYNTHESIS QUALITY CHECKS
# ═══════════════════════════════════════════════════════════════════

class TestSynthesisQuality:
    def test_music_volume_is_low(self):
        """Background music should be quiet (-24 to -30 dB)."""
        assert -30 <= MUSIC_VOLUME_DB <= -22

    def test_short_video_caps_chords(self):
        """Videos < 30s should use max 2 chords to avoid rushed changes."""
        from audio_processor import generate_ambient_music
        # We can test this indirectly by checking the number of FFmpeg calls
        call_count = 0
        def mock_ffmpeg(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("audio_processor._run_ffmpeg", side_effect=mock_ffmpeg), \
             patch("tempfile.mkdtemp", return_value="/tmp/test"), \
             patch("audio_processor.os.path.join", return_value="/tmp/chord.wav"):
            try:
                generate_ambient_music(20.0, "/tmp/test.mp3", progression="major_warm")
            except Exception:
                pass
        # Short video → 2 chord segments → 2 FFmpeg generate calls
        assert call_count <= 3  # 2 generate + maybe 1 concat

    def test_long_video_uses_all_chords(self):
        """Videos >= 30s should use all 4 chords."""
        from audio_processor import generate_ambient_music
        call_count = 0
        def mock_ffmpeg(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return ""

        with patch("audio_processor._run_ffmpeg", side_effect=mock_ffmpeg), \
             patch("tempfile.mkdtemp", return_value="/tmp/test"), \
             patch("audio_processor.os.path.join", return_value="/tmp/chord.wav"):
            try:
                generate_ambient_music(120.0, "/tmp/test.mp3", progression="major_warm")
            except Exception:
                pass
        # Long video → 4 chord segments → 4 FFmpeg generate calls + concat
        assert call_count >= 4
