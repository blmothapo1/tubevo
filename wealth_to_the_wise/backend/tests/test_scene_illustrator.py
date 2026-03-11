# filepath: backend/tests/test_scene_illustrator.py
"""
Tests for scene_illustrator.py — AI-Generated Scene Illustrations.

Covers:
- Prompt engineering (basic + GPT-powered)
- DALL-E 3 image generation (mocked)
- Image → animated clip conversion (mocked FFmpeg)
- Full pipeline: generate_illustrations_for_scenes
- Error handling & fallbacks
- Quality profile integration (ai_illustrations flag)
- Drop-in compatibility with stock_footage output format
"""

from __future__ import annotations

import json
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ── Mock ScenePlan (avoids importing from scene_planner) ─────────────

@dataclass
class MockScenePlan:
    label: str = "body-1"
    text: str = "Compound interest is the 8th wonder of the world."
    word_count: int = 9
    estimated_duration: float = 8.0
    queries: list = None
    style: str = "cinematic"
    clip_count: int = 1

    def __post_init__(self):
        if self.queries is None:
            self.queries = ["compound interest growth"]


# ══════════════════════════════════════════════════════════════════════
# 1.  PROMPT ENGINEERING TESTS
# ══════════════════════════════════════════════════════════════════════

class TestBuildScenePrompt:
    """Test basic (non-GPT) prompt generation."""

    def test_basic_prompt_contains_scene_text(self):
        from scene_illustrator import _build_scene_prompt
        prompt = _build_scene_prompt(
            "Invest $100 monthly for 40 years",
            "body-1", 1, 5,
        )
        assert "Invest $100 monthly" in prompt

    def test_prompt_has_style_directive(self):
        from scene_illustrator import _build_scene_prompt
        prompt = _build_scene_prompt("Save money", "intro", 0, 3)
        assert "illustration" in prompt.lower() or "cinematic" in prompt.lower()

    def test_prompt_has_negative_suffix(self):
        from scene_illustrator import _build_scene_prompt, NEGATIVE_PROMPT_SUFFIX
        prompt = _build_scene_prompt("Budget planning tips", "body-2", 2, 5)
        assert "no text" in prompt.lower()

    def test_intro_gets_cinematic_style(self):
        from scene_illustrator import _build_scene_prompt
        prompt = _build_scene_prompt("Welcome to wealth building", "intro", 0, 5)
        # Intro maps to "cinematic" style
        assert "cinematic" in prompt.lower()

    def test_conclusion_gets_cinematic_style(self):
        from scene_illustrator import _build_scene_prompt
        prompt = _build_scene_prompt("Start investing today", "conclusion", 4, 5)
        assert "cinematic" in prompt.lower()

    def test_long_text_truncated(self):
        from scene_illustrator import _build_scene_prompt
        long_text = "word " * 200  # 1000 chars
        prompt = _build_scene_prompt(long_text, "body-1", 1, 5)
        # Source text should be truncated to 500 chars
        assert len(prompt) < 1500  # reasonable upper bound

    def test_body_scenes_get_varied_styles(self):
        from scene_illustrator import _build_scene_prompt
        prompts = [
            _build_scene_prompt("Topic " + str(i), f"body-{i}", i, 10, style_seed="test")
            for i in range(10)
        ]
        # Not all prompts should be identical in style — at least some variety
        unique_prompts = set(prompts)
        assert len(unique_prompts) > 1


class TestBuildScenePromptsWithAI:
    """Test GPT-powered prompt generation."""

    def test_falls_back_without_api_key(self):
        from scene_illustrator import _build_scene_prompts_with_ai
        plans = [MockScenePlan(label="intro", text="Hello")]
        prompts = _build_scene_prompts_with_ai(plans, openai_api_key="")
        assert len(prompts) == 1
        assert "Hello" in prompts[0]

    @patch("scene_illustrator.requests.post")
    def test_gpt_prompt_generation(self, mock_post):
        from scene_illustrator import _build_scene_prompts_with_ai

        # Mock GPT response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "prompts": [
                            "A golden seed growing into a money tree, cinematic",
                            "A glowing shield protecting a house from storm",
                        ]
                    })
                }
            }]
        }
        mock_post.return_value = mock_resp

        plans = [
            MockScenePlan(label="intro", text="Compound interest"),
            MockScenePlan(label="body-1", text="Emergency fund"),
        ]
        prompts = _build_scene_prompts_with_ai(plans, openai_api_key="sk-test")
        assert len(prompts) == 2
        assert "money tree" in prompts[0].lower()

    @patch("scene_illustrator.requests.post")
    def test_gpt_failure_falls_back(self, mock_post):
        from scene_illustrator import _build_scene_prompts_with_ai

        mock_post.side_effect = Exception("API error")
        plans = [MockScenePlan(label="intro", text="Hello world")]
        prompts = _build_scene_prompts_with_ai(plans, openai_api_key="sk-test")
        assert len(prompts) == 1
        assert "Hello world" in prompts[0]

    @patch("scene_illustrator.requests.post")
    def test_gpt_wrong_count_gets_padded(self, mock_post):
        from scene_illustrator import _build_scene_prompts_with_ai

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({"prompts": ["Only one prompt"]})
                }
            }]
        }
        mock_post.return_value = mock_resp

        plans = [
            MockScenePlan(label="intro", text="Scene 1"),
            MockScenePlan(label="body-1", text="Scene 2"),
            MockScenePlan(label="conclusion", text="Scene 3"),
        ]
        prompts = _build_scene_prompts_with_ai(plans, openai_api_key="sk-test")
        assert len(prompts) == 3

    @patch("scene_illustrator.requests.post")
    def test_negative_suffix_added_if_missing(self, mock_post):
        from scene_illustrator import _build_scene_prompts_with_ai

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "prompts": ["A beautiful illustration without negative suffix"]
                    })
                }
            }]
        }
        mock_post.return_value = mock_resp

        plans = [MockScenePlan(label="intro", text="Test")]
        prompts = _build_scene_prompts_with_ai(plans, openai_api_key="sk-test")
        assert "no text" in prompts[0].lower()


# ══════════════════════════════════════════════════════════════════════
# 2.  DALL-E IMAGE GENERATION TESTS
# ══════════════════════════════════════════════════════════════════════

class TestGenerateImage:
    """Test DALL-E 3 API calls (mocked)."""

    @patch("scene_illustrator.requests.get")
    @patch("scene_illustrator.requests.post")
    def test_successful_image_generation(self, mock_post, mock_get, tmp_path):
        from scene_illustrator import _generate_image

        # Mock DALL-E response
        mock_dalle_resp = MagicMock()
        mock_dalle_resp.raise_for_status = MagicMock()
        mock_dalle_resp.json.return_value = {
            "data": [{"url": "https://example.com/image.png"}]
        }
        mock_post.return_value = mock_dalle_resp

        # Mock image download
        mock_img_resp = MagicMock()
        mock_img_resp.raise_for_status = MagicMock()
        mock_img_resp.content = b"\x89PNG\r\n" + b"\x00" * 100
        mock_get.return_value = mock_img_resp

        output = str(tmp_path / "test.png")
        result = _generate_image("test prompt", output, openai_api_key="sk-test")
        assert result == output
        assert os.path.exists(output)

    @patch("scene_illustrator.requests.post")
    def test_rate_limit_retries(self, mock_post, tmp_path):
        import requests as req
        from scene_illustrator import _generate_image

        # First call: 429 rate limit, second call: success
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.raise_for_status.side_effect = req.exceptions.HTTPError(response=mock_429)

        mock_ok = MagicMock()
        mock_ok.raise_for_status = MagicMock()
        mock_ok.json.return_value = {
            "data": [{"url": "https://example.com/image.png"}]
        }

        mock_post.side_effect = [mock_429, mock_ok]

        with patch("scene_illustrator.requests.get") as mock_get:
            mock_img = MagicMock()
            mock_img.raise_for_status = MagicMock()
            mock_img.content = b"\x89PNG" + b"\x00" * 50
            mock_get.return_value = mock_img

            with patch("scene_illustrator.time.sleep"):  # Don't actually sleep
                output = str(tmp_path / "retry.png")
                result = _generate_image("test", output, openai_api_key="sk-test")
                assert result == output

    @patch("scene_illustrator.requests.post")
    def test_content_policy_rejection_retries_with_safe_prompt(self, mock_post, tmp_path):
        import requests as req
        from scene_illustrator import _generate_image

        # First call: 400 content policy, second call: success
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.raise_for_status.side_effect = req.exceptions.HTTPError(response=mock_400)

        mock_ok = MagicMock()
        mock_ok.raise_for_status = MagicMock()
        mock_ok.json.return_value = {
            "data": [{"url": "https://example.com/safe.png"}]
        }

        mock_post.side_effect = [mock_400, mock_ok]

        with patch("scene_illustrator.requests.get") as mock_get:
            mock_img = MagicMock()
            mock_img.raise_for_status = MagicMock()
            mock_img.content = b"\x89PNG" + b"\x00" * 50
            mock_get.return_value = mock_img

            with patch("scene_illustrator.time.sleep"):
                output = str(tmp_path / "safe.png")
                result = _generate_image("risky prompt", output, openai_api_key="sk-test")
                assert result == output

    @patch("scene_illustrator.requests.post")
    def test_all_retries_exhausted_raises(self, mock_post, tmp_path):
        from scene_illustrator import _generate_image
        from pipeline_errors import ExternalServiceError

        mock_post.side_effect = Exception("Network error")

        with patch("scene_illustrator.time.sleep"):
            with pytest.raises(ExternalServiceError):
                _generate_image("test", str(tmp_path / "fail.png"), openai_api_key="sk-test")


# ══════════════════════════════════════════════════════════════════════
# 3.  IMAGE → ANIMATED CLIP TESTS
# ══════════════════════════════════════════════════════════════════════

class TestImageToAnimatedClip:
    """Test FFmpeg-based image animation."""

    @patch("scene_illustrator.subprocess.run")
    def test_clip_generation_calls_ffmpeg(self, mock_run, tmp_path):
        from scene_illustrator import _image_to_animated_clip

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        img = str(tmp_path / "test.png")
        Path(img).touch()
        out = str(tmp_path / "clip.mp4")

        result = _image_to_animated_clip(img, out, 8.0)
        assert result == out
        mock_run.assert_called_once()

        # Verify FFmpeg command includes zoompan
        cmd_args = mock_run.call_args[0][0]
        vf_arg = cmd_args[cmd_args.index("-vf") + 1]
        assert "zoompan" in vf_arg

    @patch("scene_illustrator.subprocess.run")
    def test_all_animation_directions(self, mock_run, tmp_path):
        from scene_illustrator import _image_to_animated_clip, _ANIMATION_DIRECTIONS

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        img = str(tmp_path / "test.png")
        Path(img).touch()

        for direction in _ANIMATION_DIRECTIONS:
            out = str(tmp_path / f"clip_{direction}.mp4")
            _image_to_animated_clip(img, out, 5.0, direction=direction)

        assert mock_run.call_count == len(_ANIMATION_DIRECTIONS)

    @patch("scene_illustrator.subprocess.run")
    def test_short_duration_clamp(self, mock_run, tmp_path):
        from scene_illustrator import _image_to_animated_clip

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        img = str(tmp_path / "test.png")
        Path(img).touch()

        # Very short duration — should still produce at least 1 second
        _image_to_animated_clip(img, str(tmp_path / "short.mp4"), 0.3)
        cmd_args = mock_run.call_args[0][0]
        vf_arg = cmd_args[cmd_args.index("-vf") + 1]
        assert "zoompan" in vf_arg

    @patch("scene_illustrator.subprocess.run")
    def test_ffmpeg_failure_raises(self, mock_run, tmp_path):
        from scene_illustrator import _image_to_animated_clip

        mock_run.return_value = MagicMock(returncode=1, stderr="Error encoding")
        img = str(tmp_path / "test.png")
        Path(img).touch()

        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            _image_to_animated_clip(img, str(tmp_path / "fail.mp4"), 5.0)

    @patch("scene_illustrator.subprocess.run")
    def test_ffmpeg_timeout_raises(self, mock_run, tmp_path):
        import subprocess
        from scene_illustrator import _image_to_animated_clip

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)
        img = str(tmp_path / "test.png")
        Path(img).touch()

        with pytest.raises(RuntimeError, match="timed out"):
            _image_to_animated_clip(img, str(tmp_path / "timeout.mp4"), 5.0)


class TestPickDirection:
    """Test deterministic direction selection."""

    def test_deterministic_with_same_seed(self):
        from scene_illustrator import _pick_direction
        d1 = _pick_direction(3, seed="topic-a")
        d2 = _pick_direction(3, seed="topic-a")
        assert d1 == d2

    def test_varies_across_scenes(self):
        from scene_illustrator import _pick_direction
        directions = [_pick_direction(i, seed="test") for i in range(20)]
        unique = set(directions)
        assert len(unique) > 1

    def test_returns_valid_direction(self):
        from scene_illustrator import _pick_direction, _ANIMATION_DIRECTIONS
        for i in range(10):
            d = _pick_direction(i)
            assert d in _ANIMATION_DIRECTIONS


# ══════════════════════════════════════════════════════════════════════
# 4.  FULL PIPELINE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestGenerateIllustrationsForScenes:
    """Test the main entry point."""

    def test_requires_openai_key(self):
        from scene_illustrator import generate_illustrations_for_scenes
        from pipeline_errors import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="OpenAI API key"):
            generate_illustrations_for_scenes(
                [MockScenePlan()],
                openai_api_key="",
            )

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_full_pipeline_success(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Intro text", estimated_duration=10.0),
            MockScenePlan(label="body-1", text="Body text", estimated_duration=15.0),
            MockScenePlan(label="conclusion", text="Outro text", estimated_duration=8.0),
        ]

        mock_prompts.return_value = [
            "Prompt for intro",
            "Prompt for body",
            "Prompt for conclusion",
        ]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_clip(image_path, output_path, duration, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_clip.side_effect = fake_clip

        with patch("scene_illustrator.time.sleep"):
            result = generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                topic="Wealth Building",
                clips_dir=tmp_path,
            )

        assert len(result) == 3
        assert result[0]["label"] == "intro"
        assert result[1]["label"] == "body-1"
        assert result[2]["label"] == "conclusion"
        assert len(result[0]["clips"]) == 1
        assert result[0]["duration"] == 10.0

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_partial_failure_still_returns(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Good scene", estimated_duration=10.0),
            MockScenePlan(label="body-1", text="Bad scene", estimated_duration=15.0),
        ]

        mock_prompts.return_value = ["Good prompt", "Bad prompt"]

        call_count = [0]

        def fake_generate(prompt, output_path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("DALL-E failed for this one")
            Path(output_path).touch()
            return output_path

        def fake_clip(image_path, output_path, duration, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_clip.side_effect = fake_clip

        with patch("scene_illustrator.time.sleep"):
            result = generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                clips_dir=tmp_path,
            )

        assert len(result) == 2
        # First scene succeeded, second failed
        assert len(result[0]["clips"]) == 1
        assert len(result[1]["clips"]) == 0

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_all_failures_raises(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        from scene_illustrator import generate_illustrations_for_scenes
        from pipeline_errors import ExternalServiceError

        plans = [MockScenePlan(label="intro", text="Test")]
        mock_prompts.return_value = ["Prompt"]
        mock_gen.side_effect = Exception("All fail")

        with patch("scene_illustrator.time.sleep"):
            with pytest.raises(ExternalServiceError, match="Could not generate"):
                generate_illustrations_for_scenes(
                    plans,
                    openai_api_key="sk-test",
                    clips_dir=tmp_path,
                )

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_output_format_matches_stock_footage(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        """Verify output format is drop-in compatible with stock_footage output."""
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Test", estimated_duration=10.0),
        ]
        mock_prompts.return_value = ["Test prompt"]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_clip(image_path, output_path, duration, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_clip.side_effect = fake_clip

        with patch("scene_illustrator.time.sleep"):
            result = generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                clips_dir=tmp_path,
            )

        # Must have same keys as stock_footage.download_clips_for_scenes()
        for entry in result:
            assert "label" in entry
            assert "clips" in entry
            assert "duration" in entry
            assert isinstance(entry["clips"], list)
            assert isinstance(entry["duration"], (int, float))

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_cleans_old_clips(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        from scene_illustrator import generate_illustrations_for_scenes

        # Create old files
        (tmp_path / "clip_0.mp4").touch()
        (tmp_path / "clip_99.mp4").touch()
        (tmp_path / "scene_000.png").touch()

        plans = [MockScenePlan(label="intro", text="Test", estimated_duration=5.0)]
        mock_prompts.return_value = ["Test"]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_clip(image_path, output_path, duration, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_clip.side_effect = fake_clip

        with patch("scene_illustrator.time.sleep"):
            generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                clips_dir=tmp_path,
            )

        # Old clip_99 should be cleaned
        assert not (tmp_path / "clip_99.mp4").exists()


# ══════════════════════════════════════════════════════════════════════
# 5.  QUALITY PROFILE INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════

class TestQualityProfileIntegration:
    """Test that ai_illustrations flag is properly set in quality profiles."""

    def test_free_no_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["free"]["ai_illustrations"] is False

    def test_starter_no_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["starter"]["ai_illustrations"] is False

    def test_pro_has_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_illustrations"] is True

    def test_agency_has_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_illustrations"] is True

    def test_agency_hd_quality(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_image_quality"] == "hd"

    def test_pro_standard_quality(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_image_quality"] == "standard"

    def test_free_has_quality_field(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert "ai_image_quality" in PLAN_QUALITY_PROFILES["free"]


# ══════════════════════════════════════════════════════════════════════
# 6.  ILLUSTRATION STYLE TESTS
# ══════════════════════════════════════════════════════════════════════

class TestIllustrationStyles:
    """Test style presets and mappings."""

    def test_all_styles_have_descriptions(self):
        from scene_illustrator import ILLUSTRATION_STYLES
        for name, desc in ILLUSTRATION_STYLES.items():
            assert isinstance(desc, str)
            assert len(desc) > 20
            assert name in ("cinematic", "finance", "documentary", "modern", "conceptual")

    def test_scene_style_map_covers_intro_conclusion(self):
        from scene_illustrator import SCENE_STYLE_MAP
        assert "intro" in SCENE_STYLE_MAP
        assert "conclusion" in SCENE_STYLE_MAP

    def test_negative_prompt_suffix(self):
        from scene_illustrator import NEGATIVE_PROMPT_SUFFIX
        assert "no text" in NEGATIVE_PROMPT_SUFFIX.lower()
        assert "no watermarks" in NEGATIVE_PROMPT_SUFFIX.lower()


# ══════════════════════════════════════════════════════════════════════
# 7.  ANIMATION DIRECTIONS
# ══════════════════════════════════════════════════════════════════════

class TestAnimationDirections:
    """Test the animation direction catalog."""

    def test_has_variety(self):
        from scene_illustrator import _ANIMATION_DIRECTIONS
        assert len(_ANIMATION_DIRECTIONS) >= 6

    def test_includes_zoom_types(self):
        from scene_illustrator import _ANIMATION_DIRECTIONS
        zoom_types = [d for d in _ANIMATION_DIRECTIONS if "zoom" in d]
        assert len(zoom_types) >= 2

    def test_includes_pan_types(self):
        from scene_illustrator import _ANIMATION_DIRECTIONS
        pan_types = [d for d in _ANIMATION_DIRECTIONS if "pan" in d]
        assert len(pan_types) >= 2
