"""
upload_history.py — Persistent record of uploaded videos.

Tracks every successful YouTube upload in a local JSON file to:
  • Prevent duplicate uploads (same file or same title)
  • Provide a persistent log of what has been published
  • Allow post-failure recovery (know what already went live)

Usage:
    from upload_history import is_duplicate, record_upload, get_history

    if is_duplicate(file_path="output/my_video.mp4", title="My Title"):
        print("Already uploaded!")
    else:
        record_upload(video_id="abc123", title="My Title", file_path="output/my_video.mp4")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("wealth_to_the_wise.upload_history")

HISTORY_FILE = Path("output") / "upload_history.json"


def _load_history() -> list[dict]:
    """Load the upload history from disk."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read upload history: %s", e)
    return []


def _save_history(history: list[dict]) -> None:
    """Write the upload history to disk."""
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _file_hash(file_path: str) -> str:
    """Compute a SHA-256 hash of the first 10 MB of a file (fast enough for
    large videos while still being a reliable fingerprint)."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read first 10 MB — sufficient to fingerprint any unique render
        data = f.read(10 * 1024 * 1024)
        h.update(data)
    return h.hexdigest()


def is_duplicate(*, file_path: str | None = None, title: str | None = None) -> bool:
    """Check whether a video has already been uploaded.

    Matches on file content hash (primary) or exact title (secondary).
    Returns True if a match is found.
    """
    history = _load_history()

    if file_path and os.path.isfile(file_path):
        fhash = _file_hash(file_path)
        for entry in history:
            if entry.get("file_hash") == fhash:
                logger.warning(
                    "Duplicate detected (file hash match): already uploaded as video ID %s — '%s'",
                    entry.get("video_id"), entry.get("title"),
                )
                return True

    if title:
        for entry in history:
            if entry.get("title", "").strip().lower() == title.strip().lower():
                logger.warning(
                    "Duplicate detected (title match): already uploaded as video ID %s — '%s'",
                    entry.get("video_id"), entry.get("title"),
                )
                return True

    return False


def record_upload(
    *,
    video_id: str,
    title: str,
    file_path: str,
    metadata: dict | None = None,
) -> None:
    """Record a successful upload in the persistent history."""
    history = _load_history()

    fhash = _file_hash(file_path) if os.path.isfile(file_path) else ""

    entry = {
        "video_id": video_id,
        "title": title,
        "file_path": file_path,
        "file_hash": fhash,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
    if metadata:
        entry["tags"] = metadata.get("tags", [])
        entry["description"] = metadata.get("description", "")

    history.append(entry)
    _save_history(history)
    logger.info("Upload recorded in history: %s — '%s'", video_id, title)


def get_history() -> list[dict]:
    """Return the full upload history."""
    return _load_history()


# ── CLI helper ──────────────────────────────────────────────────────
if __name__ == "__main__":
    h = get_history()
    if not h:
        print("No uploads recorded yet.")
    else:
        for entry in h:
            print(f"  {entry['uploaded_at']}  {entry['video_id']}  {entry['title']}")
