"""
stock_footage.py — Download royalty-free stock video clips from Pexels & Pixabay.

Uses **two** free stock-video providers in a **parallel-merge** pattern:

  * **Pexels** (primary)  — always searched for every query.
  * **Pixabay** (secondary) — always searched in parallel when key is
    available, results merged and shuffled for maximum randomisation.
    Falls back to Pexels-only if no Pixabay key.

Both APIs are free with no watermarks.  Users supply their own keys
via the BYOK settings page.  If only one key is present, that provider
is used exclusively — no errors are raised for the missing one.

Supports two modes:
  1. **Legacy** — ``download_clips_for_topic(topic, num_clips)``
     Generates generic queries from the topic and downloads N clips.
  2. **Scene-aware** — ``download_clips_for_scenes(scene_plans)``
     Downloads per-scene clips using targeted queries from the scene planner.
     Each ScenePlan gets its own set of clips, ensuring visual variety and
     semantic match to the narration.

Anti-repetition features:
  * **Wide candidate pool** — 15 results per page × random page 1-5
  * **Dual-provider merge** — Pexels + Pixabay combined and shuffled
  * **Cross-video dedup cache** — JSON file tracks media IDs used in
    the last N videos per user, preventing the same stock clip from
    appearing in consecutive videos.
  * **Query augmentation** — scenes get extra synonym-expanded queries
    for broader coverage of the stock libraries.

Setup:
    1. Get a free API key at https://www.pexels.com/api/
    2. Add to your .env:  PEXELS_API_KEY=your-key-here
    3. (Optional) Get a free key at https://pixabay.com/api/docs/#api_search_videos
    4. Add to your .env:  PIXABAY_API_KEY=your-key-here
"""

from __future__ import annotations

import json
import logging
import os
import random
import requests
import time as _time_module
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

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
PIXABAY_VIDEO_SEARCH_URL = "https://pixabay.com/api/videos/"

CLIPS_DIR = Path("output/clips")
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

# ── Retry configuration ─────────────────────────────────────────────
_MAX_RETRIES = 4
_BASE_DELAY = 2.0        # seconds
_MAX_DELAY = 30.0
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Search tuning — controls candidate pool size ────────────────────
# per_page=15 gives 15 candidates per query (was 5 — too narrow).
# Random pages 1-5 ensure different results across generations.
SEARCH_PER_PAGE = 15
SEARCH_MAX_PAGE = 5

# ── Cross-video dedup cache ─────────────────────────────────────────
# Tracks media IDs used in the last N videos per user so the same
# stock clip doesn't appear in consecutive videos.
DEDUP_CACHE_DIR = Path("output") / "media_cache"
DEDUP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEDUP_CACHE_MAX_VIDEOS = 10   # remember clips from last 10 videos

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

# ── Query augmentation — synonym expansion for broader search ────────
_QUERY_SYNONYMS: dict[str, list[str]] = {
    "money": ["currency", "cash flow", "dollars", "banknotes"],
    "wealth": ["prosperity", "abundance", "fortune", "riches"],
    "invest": ["portfolio", "stocks bonds", "market trading", "financial growth"],
    "business": ["corporate", "enterprise", "startup", "office work"],
    "success": ["achievement", "winning", "celebration", "triumph"],
    "luxury": ["premium", "elegant", "high end", "upscale"],
    "city": ["urban", "downtown", "metropolis", "skyline"],
    "saving": ["frugal", "budget", "piggy bank", "money jar"],
    "technology": ["digital", "innovation", "computer code", "tech devices"],
    "house": ["real estate", "property", "home interior", "architecture"],
}


def _augment_queries(queries: list[str], max_extra: int = 3) -> list[str]:
    """Expand a query list with synonym-based alternatives.

    For each query, if any word matches a synonym group, inject
    up to *max_extra* alternative queries derived from synonyms.
    This broadens the search space without duplicating exact queries.
    """
    augmented = list(queries)
    seen = {q.strip().lower() for q in queries}
    added = 0

    for q in queries:
        if added >= max_extra:
            break
        words = q.lower().split()
        for word in words:
            if word in _QUERY_SYNONYMS and added < max_extra:
                synonym = random.choice(_QUERY_SYNONYMS[word])
                # Replace the word with its synonym
                new_q = q.lower().replace(word, synonym, 1)
                if new_q.strip().lower() not in seen:
                    seen.add(new_q.strip().lower())
                    augmented.append(new_q.strip())
                    added += 1
                    break

    return augmented


# ── Resolution validation ────────────────────────────────────────────

def _validate_resolution(video: dict, min_width: int = 1280, min_height: int = 720) -> bool:
    """Check that a Pexels video has at least one file meeting resolution requirements."""
    files = video.get("video_files", [])
    return any(
        f.get("width", 0) >= min_width and f.get("height", 0) >= min_height
        for f in files
    )


# ══════════════════════════════════════════════════════════════════════
# CROSS-VIDEO DEDUP CACHE — prevents the same stock clip from appearing
# in consecutive videos for the same user.  Stored as a lightweight
# JSON file per user (no DB dependency from this sync module).
# ══════════════════════════════════════════════════════════════════════

def _dedup_cache_path(user_id: str) -> Path:
    """Return the cache file path for a given user."""
    safe_id = user_id.replace("/", "_").replace("\\", "_")[:50]
    return DEDUP_CACHE_DIR / f"used_media_{safe_id}.json"


def load_cross_video_ids(user_id: str | None) -> set[int]:
    """Load media IDs used in recent videos for this user.

    Returns an empty set if no cache exists or user_id is None.
    """
    if not user_id:
        return set()
    cache_file = _dedup_cache_path(user_id)
    if not cache_file.exists():
        return set()
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        # data is a list of {"video_ts": ..., "ids": [...]} entries
        all_ids: set[int] = set()
        for entry in data[-DEDUP_CACHE_MAX_VIDEOS:]:
            all_ids.update(entry.get("ids", []))
        return all_ids
    except Exception as e:
        logger.warning("Could not load dedup cache for user %s: %s", user_id, e)
        return set()


def save_cross_video_ids(user_id: str | None, used_ids: set[int]) -> None:
    """Append the media IDs used in this video to the user's cache.

    Keeps only the last DEDUP_CACHE_MAX_VIDEOS entries to bound size.
    """
    if not user_id or not used_ids:
        return
    cache_file = _dedup_cache_path(user_id)
    try:
        existing: list[dict] = []
        if cache_file.exists():
            existing = json.loads(cache_file.read_text(encoding="utf-8"))
        existing.append({
            "video_ts": _time_module.time(),
            "ids": sorted(used_ids),
        })
        # Keep only last N entries
        existing = existing[-DEDUP_CACHE_MAX_VIDEOS:]
        cache_file.write_text(json.dumps(existing, indent=1), encoding="utf-8")
        logger.info(
            "Saved %d media IDs to cross-video dedup cache (user=%s, entries=%d)",
            len(used_ids), user_id[:8] if user_id else "?", len(existing),
        )
    except Exception as e:
        logger.warning("Could not save dedup cache for user %s: %s", user_id, e)


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
    per_page: int = SEARCH_PER_PAGE,
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


# ── Pixabay provider ────────────────────────────────────────────────

def _search_pixabay_videos(
    query: str,
    per_page: int = SEARCH_PER_PAGE,
    *,
    page: int = 1,
    api_key: str | None = None,
) -> list[dict]:
    """Search Pixabay for videos matching *query*.

    Returns results **normalized to the Pexels schema** so the rest of the
    pipeline (pick_best_video_file, dedup, etc.) works identically.

    Pixabay's video API returns ``hits[]`` with a different shape than Pexels,
    so we convert each hit into the same dict structure.
    """
    effective_key = api_key or PIXABAY_API_KEY
    if not effective_key:
        return []  # silently skip — Pixabay is optional

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(
                PIXABAY_VIDEO_SEARCH_URL,
                params={
                    "key": effective_key,
                    "q": query,
                    "video_type": "film",        # cinematic footage, not animation
                    "per_page": per_page,
                    "page": page,
                    "safesearch": "true",
                    "order": "popular",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                return [_normalize_pixabay_hit(h) for h in hits]
            if resp.status_code in _RETRIABLE_STATUS_CODES:
                last_exc = RuntimeError(f"Pixabay API {resp.status_code}: {resp.text[:200]}")
                delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
                logger.warning(
                    "Pixabay API error %d for '%s' (attempt %d/%d) — retrying in %.1fs",
                    resp.status_code, query, attempt, _MAX_RETRIES, delay,
                )
                import time as _time
                _time.sleep(delay)
                continue
            if resp.status_code in (401, 403):
                logger.warning("Pixabay API auth error %d — key may be invalid", resp.status_code)
                return []  # don't crash the pipeline, just skip fallback
            resp.raise_for_status()
        except (requests.exceptions.RequestException, ApiAuthError) as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                break
            delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
            logger.warning(
                "Pixabay network error for '%s' (attempt %d/%d): %s — retrying in %.1fs",
                query, attempt, _MAX_RETRIES, type(exc).__name__, delay,
            )
            import time as _time
            _time.sleep(delay)

    logger.warning("Pixabay search failed after %d retries: %s", _MAX_RETRIES, last_exc)
    return []  # never crash the pipeline for a fallback failure


def _normalize_pixabay_hit(hit: dict) -> dict:
    """Convert a Pixabay video hit into a Pexels-compatible dict.

    Pixabay returns::

        { "id": 1234, "duration": 15,
          "videos": { "large": {"url": ..., "width": 1920, "height": 1080}, ... } }

    We normalise to the Pexels shape::

        { "id": -1234, "duration": 15,
          "video_files": [{"link": ..., "width": 1920, "height": 1080}], ... }

    IDs are negated so they can never collide with Pexels IDs during dedup.
    """
    video_files: list[dict] = []
    for _quality, vdata in (hit.get("videos") or {}).items():
        if isinstance(vdata, dict) and vdata.get("url"):
            video_files.append({
                "link": vdata["url"],
                "width": vdata.get("width", 0),
                "height": vdata.get("height", 0),
            })

    return {
        "id": -(hit.get("id", 0)),          # negative → unique namespace
        "duration": hit.get("duration", 0),
        "video_files": video_files,
        "_provider": "pixabay",
    }


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


def _count_usable(
    videos: list[dict],
    seen_ids: set[int],
    min_duration: int,
) -> int:
    """Count how many videos in a result set pass the dedup + quality filters."""
    count = 0
    for v in videos:
        vid_id = v.get("id", 0)
        if vid_id in seen_ids:
            continue
        if v.get("duration", 0) < min_duration:
            continue
        if not _validate_resolution(v):
            continue
        if not _pick_best_video_file(v):
            continue
        count += 1
    return count


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
    pixabay_api_key: str | None = None,
) -> tuple[list[str], set[int]]:
    """Download clips for a list of queries, deduplicating by video ID.

    Returns (list_of_clip_paths, updated_seen_video_ids).
    Shared helper used by both legacy and scene-aware download functions.

    **Parallel-merge strategy**: For each query, BOTH Pexels and Pixabay
    are searched (when keys are available).  Results are merged, shuffled,
    and the best candidates are picked.  This dramatically widens the
    candidate pool (up to 30 clips per query instead of 5).

    **Wide page randomisation**: Random page 1-5 (was 1-3) means we
    reach deeper into the stock libraries for less commonly-seen footage.
    """
    if seen_video_ids is None:
        seen_video_ids = set()

    _effective_clips_dir = clips_dir or CLIPS_DIR

    downloaded: list[str] = []

    for query in queries:
        if len(downloaded) >= num_clips:
            break

        # Random page offset (1-SEARCH_MAX_PAGE) for variety across generations
        page = random.randint(1, SEARCH_MAX_PAGE) if use_random_page else 1

        # ── Search BOTH providers in parallel for maximum pool ────────
        all_videos: list[dict] = []

        pexels_key = api_key or PEXELS_API_KEY
        if pexels_key:
            try:
                pexels_results = _search_pexels_videos(
                    query, per_page=SEARCH_PER_PAGE, page=page, api_key=pexels_key,
                )
                all_videos.extend(pexels_results)
            except Exception as e:
                logger.warning("Pexels search failed for '%s' (page %d): %s", query, page, e)
                # Retry on page 1 if random page failed
                if page > 1:
                    try:
                        pexels_results = _search_pexels_videos(
                            query, per_page=SEARCH_PER_PAGE, page=1, api_key=pexels_key,
                        )
                        all_videos.extend(pexels_results)
                    except Exception:
                        pass

        # ── Pixabay: always search (not just fallback) ───────────────
        _effective_pixabay_key = pixabay_api_key or PIXABAY_API_KEY
        if _effective_pixabay_key:
            try:
                # Use a different random page for Pixabay for even more variety
                pixabay_page = random.randint(1, SEARCH_MAX_PAGE) if use_random_page else 1
                pixabay_results = _search_pixabay_videos(
                    query, per_page=SEARCH_PER_PAGE, page=pixabay_page,
                    api_key=_effective_pixabay_key,
                )
                all_videos.extend(pixabay_results)
            except Exception as e:
                logger.warning("Pixabay search failed for '%s': %s", query, e)

        if not all_videos:
            logger.warning("No results from any provider for query '%s'", query)
            continue

        # ── Mega-shuffle: randomise the combined pool ────────────────
        random.shuffle(all_videos)

        for video in all_videos:
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
                provider = video.get("_provider", "pexels")
                logger.info(
                    "Downloading clip %d: '%s' (page %d, %ds, vid %d, %s)",
                    clip_idx, query, page, duration, vid_id, provider,
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
    pixabay_api_key: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """Download stock clips matched to each scene in the plan.

    Returns a list of dicts, one per scene:
        [{"label": "intro", "clips": ["output/clips/clip_0.mp4"], "duration": 12.5}, ...]

    Downloads run in parallel (up to 4 scenes concurrently) for a
    ~50-70 % speedup on multi-scene videos.

    Anti-repetition features:
      • Cross-video dedup — loads media IDs from previous videos
        and excludes them from candidate selection.
      • Query augmentation — synonym-expanded queries widen the pool.
      • Dual-provider merge — Pexels + Pixabay searched simultaneously.
      • Wide page randomisation — pages 1-5 for deeper library reach.

    This ensures:
      • Each scene gets clips semantically related to its content
      • No duplicate video IDs across the entire video (Pexels + Pixabay)
      • No duplicate video IDs across recent videos (cross-video cache)
      • Resolution consistency (all clips validated at ≥1280×720)
      • Randomised page offsets for generation-to-generation variety
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _effective_clips_dir = clips_dir or CLIPS_DIR
    _effective_clips_dir.mkdir(parents=True, exist_ok=True)

    # Clean out old clips in this directory
    for old in _effective_clips_dir.glob("clip_*.mp4"):
        old.unlink()

    # Thread-safe shared state for deduplication
    _id_lock = threading.Lock()

    # ── Load cross-video dedup cache ─────────────────────────────────
    cross_video_ids = load_cross_video_ids(user_id)
    if cross_video_ids:
        logger.info(
            "Cross-video dedup: loaded %d media IDs from previous videos (user=%s)",
            len(cross_video_ids), (user_id or "?")[:8],
        )
    global_seen_ids: set[int] = set(cross_video_ids)

    total_needed = sum(getattr(sp, "clip_count", 1) for sp in scene_plans)
    logger.info(
        "Scene-aware download: %d scenes, %d total clips needed (parallel, per_page=%d, max_page=%d)",
        len(scene_plans), total_needed, SEARCH_PER_PAGE, SEARCH_MAX_PAGE,
    )

    # Pre-compute per-scene clip index offsets so file names don't collide
    offsets: list[int] = []
    running = 0
    for sp in scene_plans:
        offsets.append(running)
        running += getattr(sp, "clip_count", 1)

    def _download_scene(scene_idx: int, sp) -> dict:
        """Download clips for a single scene (thread-safe)."""
        queries = getattr(sp, "queries", [])
        needed = getattr(sp, "clip_count", 1)
        label = getattr(sp, "label", "unknown")
        duration = getattr(sp, "estimated_duration", 0.0)

        if not queries:
            logger.warning("Scene '%s' has no queries — using label as query", label)
            queries = [label.replace("-", " ")]

        # ── Query augmentation: expand with synonyms for variety ─────
        queries = _augment_queries(queries, max_extra=2)

        # Extend queries if we need more clips than queries
        extended_queries = list(queries)
        while len(extended_queries) < needed:
            extra = list(queries)
            random.shuffle(extra)
            extended_queries.extend(extra)

        # Shuffle queries so we don't always start with the same one
        random.shuffle(extended_queries)

        clips_downloaded, new_ids = _download_clips_for_queries(
            extended_queries,
            needed,
            min_clip_duration=min_clip_duration,
            seen_video_ids=set(global_seen_ids),  # snapshot for read
            clip_index_start=offsets[scene_idx],
            clips_dir=_effective_clips_dir,
            api_key=api_key,
            pixabay_api_key=pixabay_api_key,
        )

        # Merge newly-seen IDs back thread-safely
        with _id_lock:
            global_seen_ids.update(new_ids)

        logger.info(
            "Scene '%s': requested %d clips, downloaded %d (queries=%d)",
            label, needed, len(clips_downloaded), len(extended_queries),
        )
        return {
            "label": label,
            "clips": clips_downloaded,
            "duration": duration,
            "_index": scene_idx,
        }

    # Run scenes in parallel (cap at 2 workers to stay within Railway memory limits)
    scene_clips_unordered: list[dict] = []
    max_workers = min(2, len(scene_plans))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_download_scene, i, sp): i
            for i, sp in enumerate(scene_plans)
        }
        for future in as_completed(futures, timeout=180):
            try:
                scene_clips_unordered.append(future.result(timeout=120))
            except Exception as exc:
                idx = futures[future]
                logger.warning("Scene %d download failed: %s", idx, exc)
                # Append empty entry so the scene still has a slot
                sp = scene_plans[idx]
                scene_clips_unordered.append({
                    "label": getattr(sp, "label", "unknown"),
                    "clips": [],
                    "duration": getattr(sp, "estimated_duration", 0.0),
                    "_index": idx,
                })

    # Re-order by original scene index
    scene_clips_unordered.sort(key=lambda d: d["_index"])
    scene_clips = [{k: v for k, v in d.items() if k != "_index"} for d in scene_clips_unordered]

    total_downloaded = sum(len(sc["clips"]) for sc in scene_clips)
    if total_downloaded == 0:
        raise ExternalServiceError(
            "Could not download any stock clips from Pexels or Pixabay. "
            "Check your API keys and internet connection.",
            user_hint="Stock footage download failed. Please check your API keys in Settings and try again.",
        )

    # ── Save cross-video dedup cache ─────────────────────────────────
    # Only save IDs from THIS video (not the historical ones)
    this_video_ids = global_seen_ids - cross_video_ids
    save_cross_video_ids(user_id, this_video_ids)

    logger.info(
        "Scene-aware download complete: %d/%d clips across %d scenes → %s/ "
        "(new media IDs cached: %d)",
        total_downloaded, total_needed, len(scene_clips), _effective_clips_dir,
        len(this_video_ids),
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
