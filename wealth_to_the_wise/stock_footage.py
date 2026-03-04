"""
stock_footage.py — Download royalty-free stock video clips from Pexels.

Uses the Pexels API (free, no watermarks) to find cinematic B-roll clips
that match a video's topic/keywords.

Supports two modes:
  1. **Legacy** — ``download_clips_for_topic(topic, num_clips)``
     Generates generic queries from the topic and downloads N clips.
  2. **Scene-aware** — ``download_clips_for_scenes(scene_plans)``
     Downloads per-scene clips using targeted queries from the scene planner.
     Each ScenePlan gets its own set of clips, ensuring visual variety and
     semantic match to the narration.

Setup:
    1. Get a free API key at https://www.pexels.com/api/
    2. Add to your .env:  PEXELS_API_KEY=your-key-here
"""

from __future__ import annotations

import json
import logging
import os
import random
import requests
from pathlib import Path
from typing import TYPE_CHECKING

import config
from pipeline_errors import ApiAuthError, ExternalServiceError

if TYPE_CHECKING:
    from scene_planner import ScenePlan

logger = logging.getLogger("tubevo.stock_footage")

# ── Config ───────────────────────────────────────────────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

CLIPS_DIR = Path("output/clips")
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# ── Retry configuration ─────────────────────────────────────────────
_MAX_RETRIES = 4
_BASE_DELAY = 2.0        # seconds
_MAX_DELAY = 30.0
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Fallback search queries (always usable for wealth/finance content) ─
FALLBACK_QUERIES = [
    "money cash bills",
    "luxury lifestyle",
    "city skyline night",
    "stock market trading",
    "business meeting office",
    "gold coins wealth",
    "credit card shopping",
    "person working laptop",
    "successful entrepreneur",
    "savings piggy bank",
    "expensive cars luxury",
    "real estate mansion",
    "walking through city",
    "coffee shop morning",
    "sunrise motivation",
    "gym workout discipline",
    "counting money hands",
    "office building exterior",
    "investment chart graph",
    "grocery shopping cart",
    "running morning exercise",
    "writing notes journal",
    "city traffic timelapse",
    "beach sunset relaxation",
]


# ── Resolution validation ────────────────────────────────────────────

def _validate_resolution(video: dict, min_width: int = 1280, min_height: int = 720) -> bool:
    """Check that a Pexels video has at least one file meeting resolution requirements."""
    files = video.get("video_files", [])
    return any(
        f.get("width", 0) >= min_width and f.get("height", 0) >= min_height
        for f in files
    )


def _generate_search_queries(topic: str, num_queries: int = 16) -> list[str]:
    """Use OpenAI to generate smart Pexels search queries from the topic.

    Falls back to curated queries if OpenAI is unavailable.
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate search queries for finding stock video footage on Pexels.\n"
                        "Given a YouTube video topic about wealth/finance, return a JSON array of "
                        f"{num_queries} short (2-4 word) search queries that would find cinematic, "
                        "visually appealing B-roll clips.\n"
                        "CRITICAL: Every query must be UNIQUE — no duplicates or near-duplicates.\n"
                        "Mix abstract/lifestyle shots with topic-specific ones.\n"
                        "Examples of good queries: 'money cash bills', 'luxury car driving', "
                        "'city skyline sunset', 'person typing laptop', 'gold bars vault'.\n"
                        "Return ONLY a JSON array of strings, no markdown."
                    ),
                },
                {"role": "user", "content": topic},
            ],
            max_tokens=300,
            temperature=1.0,  # high temp for variety
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]
        queries = json.loads(raw)
        if isinstance(queries, list) and len(queries) > 0:
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for q in queries:
                q_lower = q.strip().lower()
                if q_lower not in seen:
                    seen.add(q_lower)
                    unique.append(q.strip())
            logger.info("AI-generated search queries (%d unique): %s", len(unique), unique)
            return unique[:num_queries]
    except Exception as e:
        logger.warning("Could not generate AI queries: %s", e)

    # Fallback: pick random queries from the curated list
    chosen: list[str] = random.sample(FALLBACK_QUERIES, min(num_queries, len(FALLBACK_QUERIES)))
    logger.info("Using fallback queries: %s", chosen)
    return chosen


def _search_pexels_videos(
    query: str,
    per_page: int = 5,
    *,
    page: int = 1,
    api_key: str | None = None,
) -> list[dict]:
    """Search Pexels for videos matching *query*. Returns list of video dicts.

    The *page* parameter allows fetching different result pages to increase
    variety across generations (randomised page offsets).

    Includes exponential-backoff retry on transient HTTP errors (429, 5xx)
    and network-level failures.
    """
    effective_key = api_key or PEXELS_API_KEY
    if not effective_key:
        raise ApiAuthError(
            "PEXELS_API_KEY is not set. Get a free key at https://www.pexels.com/api/\n"
            "Add to your .env: PEXELS_API_KEY=your-key-here",
            user_hint="Please add your Pexels API key in Settings → API Keys.",
        )

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(
                PEXELS_VIDEO_SEARCH_URL,
                headers={"Authorization": effective_key},
                params={
                    "query": query,
                    "per_page": per_page,
                    "page": page,
                    "orientation": "landscape",
                    "size": "medium",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("videos", [])
            if resp.status_code in _RETRIABLE_STATUS_CODES:
                last_exc = RuntimeError(f"Pexels API {resp.status_code}: {resp.text[:200]}")
                delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
                logger.warning(
                    "Pexels API error %d for '%s' (attempt %d/%d) — retrying in %.1fs",
                    resp.status_code, query, attempt, _MAX_RETRIES, delay,
                )
                import time as _time
                _time.sleep(delay)
                continue
            # Non-retriable (401, 403, etc.) — fail immediately
            if resp.status_code in (401, 403):
                raise ApiAuthError(
                    f"Pexels API auth error {resp.status_code}",
                    user_hint="Your Pexels API key appears invalid. Please update it in Settings → API Keys.",
                )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                break
            delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
            logger.warning(
                "Pexels network error for '%s' (attempt %d/%d): %s — retrying in %.1fs",
                query, attempt, _MAX_RETRIES, type(exc).__name__, delay,
            )
            import time as _time
            _time.sleep(delay)

    raise ExternalServiceError(
        f"Pexels API call failed after {_MAX_RETRIES} retries: {last_exc}"
    ) from last_exc


def _pick_best_video_file(video: dict, target_height: int = 720) -> str | None:
    """From a Pexels video object, pick the best download URL.

    Prefers files closest to *target_height* (default 720p) for consistent
    resolution across all clips in the video.
    """
    files = video.get("video_files", [])
    if not files:
        return None

    # Filter to at least 720p landscape
    hd_files = [f for f in files if f.get("height", 0) >= 720 and f.get("width", 0) >= 1280]
    if hd_files:
        # Sort by closeness to target_height (prefer exact match)
        hd_files.sort(key=lambda f: abs(f.get("height", 0) - target_height))
        return hd_files[0].get("link")

    # Fallback: largest available
    files.sort(key=lambda f: f.get("height", 0), reverse=True)
    return files[0].get("link")


def _download_video(url: str, output_path: str) -> str:
    """Download a video file from *url* to *output_path*."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path


def _download_clips_for_queries(
    queries: list[str],
    num_clips: int,
    *,
    min_clip_duration: int = 5,
    seen_video_ids: set[int] | None = None,
    clip_index_start: int = 0,
    use_random_page: bool = True,
    clips_dir: Path | None = None,
    api_key: str | None = None,
) -> tuple[list[str], set[int]]:
    """Download clips for a list of queries, deduplicating by video ID.

    Returns (list_of_clip_paths, updated_seen_video_ids).
    Shared helper used by both legacy and scene-aware download functions.
    """
    if seen_video_ids is None:
        seen_video_ids = set()

    _effective_clips_dir = clips_dir or CLIPS_DIR

    downloaded: list[str] = []

    for query in queries:
        if len(downloaded) >= num_clips:
            break

        # Random page offset (1-3) for variety across generations
        page = random.randint(1, 3) if use_random_page else 1

        try:
            videos = _search_pexels_videos(query, per_page=5, page=page, api_key=api_key)
        except Exception as e:
            logger.warning("Pexels search failed for '%s' (page %d): %s", query, page, e)
            # Retry on page 1 if random page failed
            if page > 1:
                try:
                    videos = _search_pexels_videos(query, per_page=5, page=1, api_key=api_key)
                except Exception:
                    continue
            else:
                continue

        # Shuffle results so we don't always pick the first hit
        random.shuffle(videos)

        for video in videos:
            if len(downloaded) >= num_clips:
                break

            vid_id = video.get("id", 0)
            duration = video.get("duration", 0)

            # Skip duplicates, short clips, and low-res clips
            if vid_id in seen_video_ids:
                continue
            if duration < min_clip_duration:
                continue
            if not _validate_resolution(video):
                continue

            download_url = _pick_best_video_file(video)
            if not download_url:
                continue

            seen_video_ids.add(vid_id)
            clip_idx = clip_index_start + len(downloaded)
            clip_path = str(_effective_clips_dir / f"clip_{clip_idx}.mp4")

            try:
                logger.info(
                    "Downloading clip %d: '%s' (page %d, %ds, vid %d)",
                    clip_idx, query, page, duration, vid_id,
                )
                _download_video(download_url, clip_path)
                downloaded.append(clip_path)
            except Exception as e:
                logger.warning("Download failed for vid %d: %s", vid_id, e)

    return downloaded, seen_video_ids


# ── Scene-aware download (NEW) ───────────────────────────────────────

def download_clips_for_scenes(
    scene_plans: list,  # list[ScenePlan] — avoid import cycle
    *,
    min_clip_duration: int = 5,
    clips_dir: Path | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Download stock clips matched to each scene in the plan.

    Returns a list of dicts, one per scene:
        [{"label": "intro", "clips": ["output/clips/clip_0.mp4"], "duration": 12.5}, ...]

    This ensures:
      • Each scene gets clips semantically related to its content
      • No duplicate Pexels video IDs across the entire video
      • Resolution consistency (all clips validated at ≥1280×720)
      • Randomised page offsets for generation-to-generation variety
    """
    _effective_clips_dir = clips_dir or CLIPS_DIR
    _effective_clips_dir.mkdir(parents=True, exist_ok=True)

    # Clean out old clips in this directory
    for old in _effective_clips_dir.glob("clip_*.mp4"):
        old.unlink()

    global_seen_ids: set[int] = set()
    global_clip_index = 0
    scene_clips: list[dict] = []

    total_needed = sum(getattr(sp, "clip_count", 1) for sp in scene_plans)
    logger.info(
        "Scene-aware download: %d scenes, %d total clips needed",
        len(scene_plans), total_needed,
    )

    for sp in scene_plans:
        queries = getattr(sp, "queries", [])
        needed = getattr(sp, "clip_count", 1)
        label = getattr(sp, "label", "unknown")
        duration = getattr(sp, "estimated_duration", 0.0)

        if not queries:
            logger.warning("Scene '%s' has no queries — using label as query", label)
            queries = [label.replace("-", " ")]

        # Extend queries if we need more clips than queries
        extended_queries = list(queries)
        while len(extended_queries) < needed:
            # Append shuffled copies for more variety
            extra = list(queries)
            random.shuffle(extra)
            extended_queries.extend(extra)

        clips_downloaded, global_seen_ids = _download_clips_for_queries(
            extended_queries,
            needed,
            min_clip_duration=min_clip_duration,
            seen_video_ids=global_seen_ids,
            clip_index_start=global_clip_index,
            clips_dir=_effective_clips_dir,
            api_key=api_key,
        )

        global_clip_index += len(clips_downloaded)

        scene_clips.append({
            "label": label,
            "clips": clips_downloaded,
            "duration": duration,
        })

        logger.info(
            "Scene '%s': requested %d clips, downloaded %d",
            label, needed, len(clips_downloaded),
        )

    total_downloaded = sum(len(sc["clips"]) for sc in scene_clips)
    if total_downloaded == 0:
        raise ExternalServiceError(
            "Could not download any stock clips. "
            "Check your PEXELS_API_KEY and internet connection.",
            user_hint="Stock footage download failed. Please check your Pexels API key and try again.",
        )

    logger.info(
        "Scene-aware download complete: %d/%d clips across %d scenes → %s/",
        total_downloaded, total_needed, len(scene_clips), _effective_clips_dir,
    )
    return scene_clips


# ── Legacy download (unchanged API) ──────────────────────────────────

def download_clips_for_topic(
    topic: str,
    num_clips: int = 6,
    *,
    min_clip_duration: int = 5,
) -> list[str]:
    """Download *num_clips* stock video clips related to *topic*.

    Returns a list of local file paths to the downloaded clips.

    **Legacy API** — still works exactly as before.
    For scene-aware downloads, use ``download_clips_for_scenes()`` instead.
    """
    # Clean out old clips
    for old in CLIPS_DIR.glob("clip_*.mp4"):
        old.unlink()

    queries = _generate_search_queries(topic, num_queries=num_clips + 6)

    downloaded, _ = _download_clips_for_queries(
        queries,
        num_clips,
        min_clip_duration=min_clip_duration,
    )

    if not downloaded:
        raise ExternalServiceError(
            "Could not download any stock clips. Check your PEXELS_API_KEY and internet connection.",
            user_hint="Stock footage download failed. Please check your Pexels API key and try again.",
        )

    logger.info("Downloaded %d stock clips → %s/", len(downloaded), CLIPS_DIR)
    return downloaded


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_topic = "5 Frugal Habits That Build Wealth Fast"
    clips = download_clips_for_topic(test_topic, num_clips=4)
    for c in clips:
        size = os.path.getsize(c) / (1024 * 1024)
        logger.info("  %s  (%.1f MB)", c, size)
