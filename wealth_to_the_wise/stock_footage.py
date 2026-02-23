"""
stock_footage.py — Download royalty-free stock video clips from Pexels.

Uses the Pexels API (free, no watermarks) to find cinematic B-roll clips
that match a video's topic/keywords.

Setup:
    1. Get a free API key at https://www.pexels.com/api/
    2. Add to your .env:  PEXELS_API_KEY=your-key-here

Usage:
    from stock_footage import download_clips_for_topic

    clip_paths = download_clips_for_topic(
        topic="5 Frugal Habits That Build Wealth Fast",
        num_clips=6,
    )
    # → ["output/clips/clip_0.mp4", "output/clips/clip_1.mp4", ...]
"""

from __future__ import annotations

import json
import logging
import os
import random
import requests
from pathlib import Path

import config

logger = logging.getLogger("tubevo.stock_footage")

# ── Config ───────────────────────────────────────────────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

CLIPS_DIR = Path("output/clips")
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

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
]


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
                        "Mix abstract/lifestyle shots with topic-specific ones.\n"
                        "Examples of good queries: 'money cash bills', 'luxury car driving', "
                        "'city skyline sunset', 'person typing laptop', 'gold bars vault'.\n"
                        "Return ONLY a JSON array of strings, no markdown."
                    ),
                },
                {"role": "user", "content": topic},
            ],
            max_tokens=200,
            temperature=0.9,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]
        queries = json.loads(raw)
        if isinstance(queries, list) and len(queries) > 0:
            logger.info("AI-generated search queries: %s", queries)
            return queries[:num_queries]
    except Exception as e:
        logger.warning("Could not generate AI queries: %s", e)

    # Fallback: pick random queries from the curated list
    chosen = random.sample(FALLBACK_QUERIES, min(num_queries, len(FALLBACK_QUERIES)))
    logger.info("Using fallback queries: %s", chosen)
    return chosen


def _search_pexels_videos(query: str, per_page: int = 5) -> list[dict]:
    """Search Pexels for videos matching *query*. Returns list of video dicts."""
    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is not set. Get a free key at https://www.pexels.com/api/\n"
            "Add to your .env: PEXELS_API_KEY=your-key-here"
        )

    resp = requests.get(
        PEXELS_VIDEO_SEARCH_URL,
        headers={"Authorization": PEXELS_API_KEY},
        params={
            "query": query,
            "per_page": per_page,
            "orientation": "landscape",
            "size": "medium",  # don't need 4K, medium is fine
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def _pick_best_video_file(video: dict) -> str | None:
    """From a Pexels video object, pick the best HD download URL.

    Prefers: HD (1920x1080) → SD (1280x720) → whatever is available.
    """
    files = video.get("video_files", [])
    if not files:
        return None

    # Sort by quality: prefer HD landscape
    hd_files = [f for f in files if f.get("height", 0) >= 720 and f.get("width", 0) >= 1280]
    if hd_files:
        # Prefer 1080p but accept 720p
        hd_files.sort(key=lambda f: abs(f.get("height", 0) - 1080))
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


def download_clips_for_topic(
    topic: str,
    num_clips: int = 6,
    *,
    min_clip_duration: int = 5,
) -> list[str]:
    """Download *num_clips* stock video clips related to *topic*.

    Returns a list of local file paths to the downloaded clips.
    """
    # Clean out old clips
    for old in CLIPS_DIR.glob("clip_*.mp4"):
        old.unlink()

    queries = _generate_search_queries(topic, num_queries=num_clips + 4)

    downloaded: list[str] = []
    seen_video_ids: set[int] = set()

    for query in queries:
        if len(downloaded) >= num_clips:
            break

        try:
            videos = _search_pexels_videos(query, per_page=3)
        except Exception as e:
            logger.warning("Pexels search failed for '%s': %s", query, e)
            continue

        for video in videos:
            if len(downloaded) >= num_clips:
                break

            vid_id = video.get("id", 0)
            duration = video.get("duration", 0)

            # Skip duplicates and very short clips
            if vid_id in seen_video_ids:
                continue
            if duration < min_clip_duration:
                continue

            download_url = _pick_best_video_file(video)
            if not download_url:
                continue

            seen_video_ids.add(vid_id)
            clip_path = str(CLIPS_DIR / f"clip_{len(downloaded)}.mp4")

            try:
                logger.info("Downloading clip %d/%d: '%s' (%ds)", len(downloaded)+1, num_clips, query, duration)
                _download_video(download_url, clip_path)
                downloaded.append(clip_path)
            except Exception as e:
                logger.warning("Download failed: %s", e)

    if not downloaded:
        raise RuntimeError(
            "Could not download any stock clips. Check your PEXELS_API_KEY and internet connection."
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
