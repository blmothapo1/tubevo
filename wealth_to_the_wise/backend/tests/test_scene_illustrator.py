# filepath: backend/tests/test_scene_illustrator.py
"""
Tests for scene_illustrator.py — AI-Generated Scene Videos (DALL-E 3 + Runway).

Covers:
- Prompt engineering (basic + GPT-powered)
- DALL-E 3 image generation (mocked)
- Runway API: task creation, polling, download (mocked)
- Motion prompt builder
- FFmpeg zoompan fallback
- Full pipeline: Runway path + fallback path
- Error handling & fallbacks
- Quality profile integration (ai_video_model, ai_video_duration)
- Drop-in compatibility with stock_footage output format
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ── Mock ScenePlan ───────────────────────────────────────────────────

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
        assert "cinematic" in prompt.lower()

    def test_conclusion_gets_cinematic_style(self):
        from scene_illustrator import _build_scene_prompt
        prompt = _build_scene_prompt("Start investing today", "conclusion", 4, 5)
        assert "cinematic" in prompt.lower()

    def test_long_text_truncated(self):
        from scene_illustrator import _build_scene_prompt
        long_text = "word " * 200
        prompt = _build_scene_prompt(long_text, "body-1", 1, 5)
        assert len(prompt) < 1500

    def test_body_scenes_get_varied_styles(self):
        from scene_illustrator import _build_scene_prompt
        prompts = [
            _build_scene_prompt("Topic " + str(i), f"body-{i}", i, 10, style_seed="test")
            for i in range(10)
        ]
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

        mock_dalle_resp = MagicMock()
        mock_dalle_resp.raise_for_status = MagicMock()
        mock_dalle_resp.json.return_value = {
            "data": [{"url": "https://example.com/image.png"}]
        }
        mock_post.return_value = mock_dalle_resp

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

            with patch("scene_illustrator.time.sleep"):
                output = str(tmp_path / "retry.png")
                result = _generate_image("test", output, openai_api_key="sk-test")
                assert result == output

    @patch("scene_illustrator.requests.post")
    def test_content_policy_rejection_retries_with_safe_prompt(self, mock_post, tmp_path):
        import requests as req
        from scene_illustrator import _generate_image

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
# 3.  RUNWAY API TESTS
# ══════════════════════════════════════════════════════════════════════

class TestRunwayCreateTask:
    """Test Runway task creation."""

    @patch("scene_illustrator.requests.post")
    def test_creates_task_successfully(self, mock_post):
        from scene_illustrator import _runway_create_task

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "task-abc-123"}
        mock_post.return_value = mock_resp

        task_id = _runway_create_task(
            "data:image/png;base64,iVBORw0KGgo=",
            "Slow camera push-in",
            runway_api_key="rw-test-key",
        )
        assert task_id == "task-abc-123"

        # Verify correct API call
        call_kwargs = mock_post.call_args
        assert "/image_to_video" in call_kwargs[0][0]
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == "Bearer rw-test-key"
        assert headers["X-Runway-Version"] == "2024-11-06"

    @patch("scene_illustrator.requests.post")
    def test_passes_model_and_duration(self, mock_post):
        from scene_illustrator import _runway_create_task

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "task-xyz"}
        mock_post.return_value = mock_resp

        _runway_create_task(
            "data:image/png;base64,abc=",
            "Camera pan left",
            runway_api_key="rw-key",
            model="gen4.5",
            duration=10,
            ratio="1280:720",
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "gen4.5"
        assert payload["duration"] == 10
        assert payload["ratio"] == "1280:720"

    @patch("scene_illustrator.requests.post")
    def test_clamps_duration(self, mock_post):
        from scene_illustrator import _runway_create_task

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "task-1"}
        mock_post.return_value = mock_resp

        # Duration 0 → clamped to 2
        _runway_create_task(
            "data:image/png;base64,x=",
            "motion", runway_api_key="k",
            duration=0,
        )
        assert mock_post.call_args[1]["json"]["duration"] == 2

    @patch("scene_illustrator.requests.post")
    def test_truncates_long_prompt(self, mock_post):
        from scene_illustrator import _runway_create_task

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "task-1"}
        mock_post.return_value = mock_resp

        long_prompt = "a" * 2000
        _runway_create_task(
            "data:image/png;base64,x=",
            long_prompt, runway_api_key="k",
        )
        assert len(mock_post.call_args[1]["json"]["promptText"]) <= 1000


class TestRunwayPollTask:
    """Test Runway task polling."""

    @patch("scene_illustrator.requests.get")
    def test_succeeds_on_first_poll(self, mock_get):
        from scene_illustrator import _runway_poll_task

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "status": "SUCCEEDED",
            "output": ["https://example.com/video.mp4"],
        }
        mock_get.return_value = mock_resp

        task = _runway_poll_task("task-123", runway_api_key="rw-key", poll_interval=0.01)
        assert task["status"] == "SUCCEEDED"
        assert task["output"][0] == "https://example.com/video.mp4"

    @patch("scene_illustrator.time.sleep")
    @patch("scene_illustrator.requests.get")
    def test_polls_until_success(self, mock_get, mock_sleep):
        from scene_illustrator import _runway_poll_task

        pending = MagicMock()
        pending.raise_for_status = MagicMock()
        pending.json.return_value = {"status": "RUNNING"}

        success = MagicMock()
        success.raise_for_status = MagicMock()
        success.json.return_value = {
            "status": "SUCCEEDED",
            "output": ["https://example.com/video.mp4"],
        }

        mock_get.side_effect = [pending, pending, success]

        task = _runway_poll_task("task-123", runway_api_key="rw-key", poll_interval=0.01)
        assert task["status"] == "SUCCEEDED"
        assert mock_get.call_count == 3

    @patch("scene_illustrator.requests.get")
    def test_raises_on_failure(self, mock_get):
        from scene_illustrator import _runway_poll_task
        from pipeline_errors import ExternalServiceError

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "status": "FAILED",
            "failure": "Content moderation",
        }
        mock_get.return_value = mock_resp

        with pytest.raises(ExternalServiceError, match="Content moderation"):
            _runway_poll_task("task-123", runway_api_key="rw-key")

    @patch("scene_illustrator.time.time")
    @patch("scene_illustrator.time.sleep")
    @patch("scene_illustrator.requests.get")
    def test_raises_on_timeout(self, mock_get, mock_sleep, mock_time):
        from scene_illustrator import _runway_poll_task
        from pipeline_errors import ExternalServiceError

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"status": "RUNNING"}
        mock_get.return_value = mock_resp

        # Simulate time passing beyond max_poll_time
        mock_time.side_effect = [0, 0, 100, 200, 400]

        with pytest.raises(ExternalServiceError, match="timed out"):
            _runway_poll_task("task-123", runway_api_key="rw-key", max_poll_time=300)


class TestRunwayDownloadVideo:
    """Test Runway video download."""

    @patch("scene_illustrator.requests.get")
    def test_downloads_video(self, mock_get, tmp_path):
        from scene_illustrator import _runway_download_video

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [b"\x00\x00\x00\x1cftyp" + b"\x00" * 100]
        mock_get.return_value = mock_resp

        task = {"output": ["https://example.com/video.mp4"]}
        output = str(tmp_path / "clip.mp4")

        result = _runway_download_video(task, output)
        assert result == output
        assert os.path.exists(output)

    def test_raises_on_no_output(self, tmp_path):
        from scene_illustrator import _runway_download_video
        from pipeline_errors import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="no output"):
            _runway_download_video({"output": []}, str(tmp_path / "fail.mp4"))

    def test_raises_on_empty_url(self, tmp_path):
        from scene_illustrator import _runway_download_video
        from pipeline_errors import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="no URL"):
            _runway_download_video({"output": [{"url": ""}]}, str(tmp_path / "fail.mp4"))

    @patch("scene_illustrator.requests.get")
    def test_handles_dict_output(self, mock_get, tmp_path):
        from scene_illustrator import _runway_download_video

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [b"video_data"]
        mock_get.return_value = mock_resp

        task = {"output": [{"url": "https://example.com/v.mp4"}]}
        output = str(tmp_path / "clip.mp4")
        result = _runway_download_video(task, output)
        assert result == output


class TestGenerateAiVideo:
    """Test full Runway image-to-video pipeline."""

    @patch("scene_illustrator._runway_download_video")
    @patch("scene_illustrator._runway_poll_task")
    @patch("scene_illustrator._runway_create_task")
    def test_full_pipeline(self, mock_create, mock_poll, mock_download, tmp_path):
        from scene_illustrator import _generate_ai_video

        # Create a fake image
        img = tmp_path / "scene.png"
        img.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)

        mock_create.return_value = "task-abc"
        mock_poll.return_value = {"status": "SUCCEEDED", "output": ["https://example.com/v.mp4"]}

        out = str(tmp_path / "clip.mp4")
        mock_download.return_value = out

        result = _generate_ai_video(
            str(img), out, "Camera push-in",
            runway_api_key="rw-key",
        )
        assert result == out
        mock_create.assert_called_once()
        mock_poll.assert_called_once()
        mock_download.assert_called_once()

        # Verify data URI was created from the image
        create_args = mock_create.call_args
        assert create_args[0][0].startswith("data:image/png;base64,")

    @patch("scene_illustrator.time.sleep")
    @patch("scene_illustrator._runway_create_task")
    def test_retries_on_rate_limit(self, mock_create, mock_sleep, tmp_path):
        import requests as req
        from scene_illustrator import _generate_ai_video

        img = tmp_path / "scene.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 20)

        # First call: 429, second: success
        mock_429 = MagicMock()
        mock_429.status_code = 429
        http_err = req.exceptions.HTTPError(response=mock_429)

        mock_create.side_effect = [http_err, "task-retry"]

        with patch("scene_illustrator._runway_poll_task") as mock_poll, \
             patch("scene_illustrator._runway_download_video") as mock_dl:
            mock_poll.return_value = {"status": "SUCCEEDED", "output": ["url"]}
            out = str(tmp_path / "clip.mp4")
            mock_dl.return_value = out

            result = _generate_ai_video(
                str(img), out, "motion",
                runway_api_key="rw-key",
            )
            assert result == out
            assert mock_create.call_count == 2


# ══════════════════════════════════════════════════════════════════════
# 3b.  MOTION PROMPT TESTS
# ══════════════════════════════════════════════════════════════════════

class TestBuildMotionPrompt:
    """Test motion prompt generation for Runway."""

    def test_intro_gets_push_in(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Welcome to the video", "intro")
        assert "push-in" in prompt.lower() or "camera" in prompt.lower()

    def test_conclusion_gets_pull_back(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Start investing today", "conclusion")
        assert "pull-back" in prompt.lower() or "camera" in prompt.lower()

    def test_growth_keyword_triggers_upward(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Your wealth will grow exponentially", "body-1")
        assert "upward" in prompt.lower() or "grow" in prompt.lower()

    def test_risk_keyword_triggers_dramatic(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("The danger of market crashes", "body-2")
        assert "dramatic" in prompt.lower()

    def test_save_keyword_triggers_protective(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Always protect your emergency fund", "body-3")
        assert "protect" in prompt.lower() or "security" in prompt.lower()

    def test_plan_keyword_triggers_tracking(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Build a solid investment strategy", "body-4")
        assert "tracking" in prompt.lower() or "methodical" in prompt.lower()

    def test_default_motion(self):
        from scene_illustrator import _build_motion_prompt
        prompt = _build_motion_prompt("Something unrelated to finance keywords", "body-5")
        assert "cinematic" in prompt.lower()


# ══════════════════════════════════════════════════════════════════════
# 4.  FFMPEG ZOOMPAN FALLBACK TESTS
# ══════════════════════════════════════════════════════════════════════

class TestImageToAnimatedClip:
    """Test FFmpeg-based fallback animation."""

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
# 5.  FULL PIPELINE TESTS
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

    @patch("scene_illustrator._generate_ai_video")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_runway_path_success(self, mock_prompts, mock_gen, mock_video, tmp_path):
        """Full pipeline with Runway API key — should use AI video."""
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Intro text", estimated_duration=10.0),
            MockScenePlan(label="body-1", text="Body text", estimated_duration=15.0),
        ]

        mock_prompts.return_value = ["Prompt for intro", "Prompt for body"]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_video(image_path, output_path, motion_prompt, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_video.side_effect = fake_video

        with patch("scene_illustrator.time.sleep"):
            result = generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                runway_api_key="rw-test",
                topic="Wealth Building",
                clips_dir=tmp_path,
            )

        assert len(result) == 2
        assert result[0]["label"] == "intro"
        assert len(result[0]["clips"]) == 1
        assert result[0]["_method"] == "runway"
        assert result[1]["_method"] == "runway"
        # Runway video should have been called for each scene
        assert mock_video.call_count == 2

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_fallback_path_without_runway_key(self, mock_prompts, mock_gen, mock_clip, tmp_path):
        """Without Runway key → falls back to zoompan."""
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Intro text", estimated_duration=10.0),
        ]

        mock_prompts.return_value = ["Prompt"]

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
                runway_api_key="",  # No Runway key
                clips_dir=tmp_path,
            )

        assert len(result) == 1
        assert result[0]["_method"] == "zoompan"
        mock_clip.assert_called_once()

    @patch("scene_illustrator._image_to_animated_clip")
    @patch("scene_illustrator._generate_ai_video")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_runway_failure_falls_back_to_zoompan(
        self, mock_prompts, mock_gen, mock_video, mock_clip, tmp_path,
    ):
        """If Runway fails, should fall back to zoompan per scene."""
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [
            MockScenePlan(label="intro", text="Intro text", estimated_duration=10.0),
        ]

        mock_prompts.return_value = ["Prompt"]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_clip(image_path, output_path, duration, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_video.side_effect = Exception("Runway API error")
        mock_clip.side_effect = fake_clip

        with patch("scene_illustrator.time.sleep"):
            result = generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                runway_api_key="rw-test",
                clips_dir=tmp_path,
            )

        assert len(result) == 1
        assert len(result[0]["clips"]) == 1
        assert result[0]["_method"] == "zoompan"
        mock_clip.assert_called_once()

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
        """Verify drop-in compatibility with stock_footage output."""
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

        assert not (tmp_path / "clip_99.mp4").exists()

    @patch("scene_illustrator._generate_ai_video")
    @patch("scene_illustrator._generate_image")
    @patch("scene_illustrator._build_scene_prompts_with_ai")
    def test_passes_video_model_and_duration(self, mock_prompts, mock_gen, mock_video, tmp_path):
        """Verify ai_video_model and ai_video_duration are forwarded."""
        from scene_illustrator import generate_illustrations_for_scenes

        plans = [MockScenePlan(label="intro", text="Test", estimated_duration=5.0)]
        mock_prompts.return_value = ["Prompt"]

        def fake_generate(prompt, output_path, **kwargs):
            Path(output_path).touch()
            return output_path

        def fake_video(image_path, output_path, motion_prompt, **kwargs):
            Path(output_path).touch()
            return output_path

        mock_gen.side_effect = fake_generate
        mock_video.side_effect = fake_video

        with patch("scene_illustrator.time.sleep"):
            generate_illustrations_for_scenes(
                plans,
                openai_api_key="sk-test",
                runway_api_key="rw-test",
                clips_dir=tmp_path,
                ai_video_model="gen4.5",
                ai_video_duration=10,
            )

        # Verify the model and duration were passed through
        call_kwargs = mock_video.call_args[1]
        assert call_kwargs["model"] == "gen4.5"
        assert call_kwargs["duration"] == 10


# ══════════════════════════════════════════════════════════════════════
# 6.  QUALITY PROFILE INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════

class TestQualityProfileIntegration:
    """Test quality profiles include AI video fields."""

    def test_free_no_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["free"]["ai_illustrations"] is False

    def test_starter_no_ai_illustrations(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["starter"]["ai_illustrations"] is False

    def test_pro_has_ai_illustrations(self):
        """Pro uses stock footage (AI scene gen disabled for better quality)."""
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_illustrations"] is False

    def test_agency_has_ai_illustrations(self):
        """Agency uses stock footage (AI scene gen disabled for better quality)."""
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_illustrations"] is False

    def test_agency_hd_quality(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_image_quality"] == "hd"

    def test_pro_standard_quality(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_image_quality"] == "standard"

    def test_free_has_quality_field(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert "ai_image_quality" in PLAN_QUALITY_PROFILES["free"]

    def test_pro_has_video_model(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_video_model"] == "gen4_turbo"

    def test_agency_has_video_model(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_video_model"] == "gen4_turbo"

    def test_pro_has_video_duration(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["pro"]["ai_video_duration"] == 5

    def test_agency_has_video_duration(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert PLAN_QUALITY_PROFILES["agency"]["ai_video_duration"] == 5

    def test_free_no_video_model(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert "ai_video_model" not in PLAN_QUALITY_PROFILES["free"]

    def test_starter_no_video_model(self):
        from backend.utils import PLAN_QUALITY_PROFILES
        assert "ai_video_model" not in PLAN_QUALITY_PROFILES["starter"]


# ══════════════════════════════════════════════════════════════════════
# 7.  ILLUSTRATION STYLE TESTS
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
# 8.  ANIMATION DIRECTIONS
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


# ══════════════════════════════════════════════════════════════════════
# 9.  RUNWAY API CONSTANTS
# ══════════════════════════════════════════════════════════════════════

class TestRunwayConstants:
    """Test Runway API configuration constants."""

    def test_api_base_url(self):
        from scene_illustrator import RUNWAY_API_BASE
        assert "runwayml.com" in RUNWAY_API_BASE

    def test_api_version(self):
        from scene_illustrator import RUNWAY_API_VERSION
        assert RUNWAY_API_VERSION == "2024-11-06"

    def test_default_model(self):
        from scene_illustrator import RUNWAY_DEFAULT_MODEL
        assert RUNWAY_DEFAULT_MODEL == "gen4_turbo"

    def test_default_duration(self):
        from scene_illustrator import RUNWAY_DEFAULT_DURATION
        assert RUNWAY_DEFAULT_DURATION == 5

    def test_supported_ratios(self):
        from scene_illustrator import RUNWAY_RATIOS
        assert "1280:720" in RUNWAY_RATIOS
        assert "720:1280" in RUNWAY_RATIOS
