"""
main.py — Tubevo: automated YouTube upload pipeline.

Workflow (manual mode — default)
---------------------------------
1. Accept a topic (CLI arg or interactive prompt).
2. Generate a video script + YouTube metadata via OpenAI.
3. Save the script to disk and pause for voiceover / video production.
4. Once a finished video file is supplied, upload it to YouTube.

Workflow (full-auto mode — --auto flag)
----------------------------------------
1. Pick the next topic from the topic bank (or accept one via CLI).
2. Generate script + metadata via OpenAI.
3. Generate voiceover via ElevenLabs.
4. Build a video (voiceover + text overlay on dark background).
5. Upload to YouTube automatically.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import textwrap
from pathlib import Path

import config  # noqa: F401  (ensures .env is loaded early)
from script_generator import generate_script, generate_metadata
from uploader import upload_video, verify_video_processed, add_video_to_playlist, set_video_thumbnail
from upload_history import is_duplicate, record_upload

# ── Optional: Cloudflare R2 temporary storage ────────────────────────
# If R2 credentials are present, videos are staged in R2 before YouTube
# upload and deleted immediately after (regardless of success/failure).
_R2_ENABLED = bool(os.getenv("R2_ACCOUNT_ID") and os.getenv("R2_BUCKET_NAME"))

logger = logging.getLogger("tubevo.main")

# ── Paths ────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Step helpers (each step is its own function for easy extension) ──

def step_generate_script(topic: str) -> str:
    """Generate and save a video script. Returns the script text."""
    logger.info("═" * 60)
    logger.info("  STEP 1 — Generating video script")
    logger.info("═" * 60)
    script = generate_script(topic)

    script_path = OUTPUT_DIR / "latest_script.txt"
    script_path.write_text(script, encoding="utf-8")
    logger.info("Script saved → %s", script_path)
    logger.info("\n%s", textwrap.indent(script, "    "))
    return script


def step_generate_metadata(script: str, topic: str) -> dict:
    """Generate title, description, and tags. Returns metadata dict."""
    logger.info("═" * 60)
    logger.info("  STEP 2 — Generating YouTube metadata")
    logger.info("═" * 60)
    metadata = generate_metadata(script, topic)

    meta_path = OUTPUT_DIR / "latest_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("Metadata saved → %s", meta_path)
    logger.info("    Title : %s", metadata['title'])
    logger.info("    Tags  : %s", ', '.join(metadata.get('tags', [])))
    return metadata


def step_generate_voiceover(script: str) -> str:
    """Generate voiceover audio via ElevenLabs TTS."""
    logger.info("═" * 60)
    logger.info("  STEP 3 — Generating voiceover (ElevenLabs)")
    logger.info("═" * 60)
    from voiceover import generate_voiceover
    audio_path = generate_voiceover(script)
    return audio_path


def step_build_video(audio_path: str, title: str, script: str) -> str:
    """Assemble the final video from voiceover + text overlays."""
    logger.info("═" * 60)
    logger.info("  STEP 4 — Building video")
    logger.info("═" * 60)
    from video_builder import build_video
    video_path = build_video(audio_path=audio_path, title=title, script=script)
    return video_path


def step_generate_thumbnail(title: str) -> str:
    """Generate a branded YouTube thumbnail. Returns the image path.

    Attempts AI-generated background via DALL·E 3 if OPENAI_API_KEY is set.
    """
    logger.info("═" * 60)
    logger.info("  STEP 4b — Generating thumbnail")
    logger.info("═" * 60)
    from thumbnail import generate_thumbnail
    api_key = config.OPENAI_API_KEY or None
    thumb_path = generate_thumbnail(
        title,
        concept="ai_cinematic" if api_key else "bold_curiosity",
        openai_api_key=api_key,
    )
    return thumb_path


def step_wait_for_video() -> str:
    """Pause the pipeline and wait for the user to supply a video file."""
    logger.info("═" * 60)
    logger.info("  STEP 3 — Waiting for video file")
    logger.info("═" * 60)
    logger.info("The script is ready!  Record your voiceover, edit your video, and provide the path below.")

    while True:
        video_path = input("📂  Path to video file (or 'q' to quit): ").strip()
        if video_path.lower() in ("q", "quit", "exit"):
            logger.info("Pipeline cancelled.")
            sys.exit(0)
        if os.path.isfile(video_path):
            return video_path
        logger.warning("File not found: %s. Try again.", video_path)


def step_upload(video_path: str, metadata: dict, thumbnail_path: str | None = None) -> str | None:
    """Upload the finished video to YouTube. Returns the video ID, or None on failure."""
    logger.info("═" * 60)
    logger.info("  STEP 5 — Uploading to YouTube")
    logger.info("═" * 60)

    # ── Duplicate check ──
    if is_duplicate(file_path=video_path, title=metadata.get("title", "")):
        logger.warning("Skipping upload — this video has already been uploaded.")
        return None

    video_id = upload_video(
        file_path=video_path,
        title=metadata["title"],
        description=metadata.get("description", ""),
        tags=metadata.get("tags"),
        privacy=config.DEFAULT_PRIVACY,
        category_id=config.DEFAULT_VIDEO_CATEGORY,
    )

    # ── Record successful upload ──
    if video_id:
        record_upload(
            video_id=video_id,
            title=metadata["title"],
            file_path=video_path,
            metadata=metadata,
        )

        # ── Verify the video is actually processed on YouTube ──
        logger.info("═" * 60)
        logger.info("  STEP 6 — Verifying video is live on YouTube")
        logger.info("═" * 60)
        is_live = verify_video_processed(video_id)
        if not is_live:
            logger.warning(
                "Video %s uploaded but not yet confirmed as processed. "
                "It may still be processing — check YouTube Studio.",
                video_id,
            )

        # ── Assign to playlist ──
        logger.info("═" * 60)
        logger.info("  STEP 7 — Playlist assignment")
        logger.info("═" * 60)
        add_video_to_playlist(video_id)

        # ── Set custom thumbnail ──
        if thumbnail_path and os.path.isfile(thumbnail_path):
            logger.info("═" * 60)
            logger.info("  STEP 8 — Setting custom thumbnail")
            logger.info("═" * 60)
            set_video_thumbnail(video_id, thumbnail_path)

    return video_id


# ── Pipelines ───────────────────────────────────────────────────────

def _cleanup_after_upload(video_path: str) -> None:
    """Remove generated files after a successful upload to free disk space.

    Deletes: the rendered video, stock clips, voiceover, and thumbnail.
    Preserves: script, metadata, upload history, and pipeline log.
    """
    logger.info("═" * 60)
    logger.info("  🧹  Cleaning up generated files")
    logger.info("═" * 60)

    files_to_delete = [
        video_path,
        str(OUTPUT_DIR / "voiceover.mp3"),
        str(OUTPUT_DIR / "thumbnail.jpg"),
    ]

    # Also delete any old final_video.mp4 leftover
    old_final = str(OUTPUT_DIR / "final_video.mp4")
    if os.path.isfile(old_final) and old_final != video_path:
        files_to_delete.append(old_final)

    for fpath in files_to_delete:
        if os.path.isfile(fpath):
            try:
                os.remove(fpath)
                logger.info("    Deleted: %s", fpath)
            except OSError as e:
                logger.warning("    Could not delete %s: %s", fpath, e)

    # Delete stock footage clips
    clips_dir = OUTPUT_DIR / "clips"
    if clips_dir.is_dir():
        deleted_count = 0
        for clip_file in clips_dir.glob("clip_*.mp4"):
            try:
                clip_file.unlink()
                deleted_count += 1
            except OSError as e:
                logger.warning("    Could not delete %s: %s", clip_file, e)
        if deleted_count:
            logger.info("    Deleted %d stock clips from %s", deleted_count, clips_dir)

    logger.info("    Cleanup complete.")


def run_pipeline(topic: str, video_path: str | None = None) -> None:
    """Semi-manual pipeline: generate script + metadata, wait for video, upload."""
    script = step_generate_script(topic)
    metadata = step_generate_metadata(script, topic)
    thumbnail_path = step_generate_thumbnail(metadata["title"])

    if video_path and os.path.isfile(video_path):
        logger.info("Using supplied video: %s", video_path)
    else:
        video_path = step_wait_for_video()

    # ── R2 staging: upload → YouTube → delete (guaranteed) ──
    r2_key: str | None = None
    _r2_delete = None
    if _R2_ENABLED:
        from backend.services.storage_service import upload_to_r2, delete_from_r2
        _r2_delete = delete_from_r2
        r2_key, r2_url = upload_to_r2(video_path)
        logger.info("Staged in R2: %s", r2_url)

    try:
        video_id = step_upload(video_path, metadata, thumbnail_path=thumbnail_path)
    finally:
        if r2_key and _r2_delete:
            try:
                _r2_delete(r2_key)
            except Exception as e:
                logger.warning("R2 cleanup failed for %s: %s", r2_key, e)

    if video_id:
        _cleanup_after_upload(video_path)
        _print_complete(video_id, metadata)
    else:
        _print_upload_deferred(video_path, metadata)


def run_full_auto_pipeline(topic: str) -> None:
    """Fully automated: script → voiceover → video build → upload.
    Zero manual intervention required."""
    script = step_generate_script(topic)
    metadata = step_generate_metadata(script, topic)
    audio_path = step_generate_voiceover(script)
    video_path = step_build_video(audio_path, metadata["title"], script)
    thumbnail_path = step_generate_thumbnail(metadata["title"])

    # ── R2 staging: upload → YouTube → delete (guaranteed) ──
    r2_key: str | None = None
    _r2_delete = None
    if _R2_ENABLED:
        from backend.services.storage_service import upload_to_r2, delete_from_r2
        _r2_delete = delete_from_r2
        r2_key, r2_url = upload_to_r2(video_path)
        logger.info("Staged in R2: %s", r2_url)

    try:
        video_id = step_upload(video_path, metadata, thumbnail_path=thumbnail_path)
    finally:
        if r2_key and _r2_delete:
            try:
                _r2_delete(r2_key)
            except Exception as e:
                logger.warning("R2 cleanup failed for %s: %s", r2_key, e)

    if video_id:
        _cleanup_after_upload(video_path)
        _print_complete(video_id, metadata)
    else:
        _print_upload_deferred(video_path, metadata)


def _print_complete(video_id: str, metadata: dict) -> None:
    logger.info("═" * 60)
    logger.info("  🎉  PIPELINE COMPLETE")
    logger.info("═" * 60)
    logger.info("    Video ID : %s", video_id)
    logger.info("    Title    : %s", metadata['title'])
    logger.info("    URL      : https://www.youtube.com/watch?v=%s", video_id)


def _print_upload_deferred(video_path: str, metadata: dict) -> None:
    logger.info("═" * 60)
    logger.info("  ⏸️   PIPELINE COMPLETE (upload deferred)")
    logger.info("═" * 60)
    logger.info("    Title    : %s", metadata['title'])
    logger.info("    Video    : %s", video_path)
    logger.info("    Metadata : output/latest_metadata.json")
    logger.info("    The video was built successfully but could not be uploaded")
    logger.info("    (YouTube upload limit reached). You can retry later with:")
    logger.info('    python main.py --upload "%s"', video_path)


# ── CLI entry point ─────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tubevo — automated YouTube upload pipeline",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="Video topic. If omitted: interactive prompt (manual) or auto-pick (--auto)",
    )
    parser.add_argument(
        "--video", "-v",
        default=None,
        help="Path to a finished video file (manual mode only)",
    )
    parser.add_argument(
        "--auto", "-a",
        action="store_true",
        help="Full auto: generate script → voiceover → video → upload (no manual steps)",
    )
    parser.add_argument(
        "--upload", "-u",
        default=None,
        help="Retry uploading a previously built video (reads metadata from output/latest_metadata.json)",
    )
    args = parser.parse_args()

    # ── Upload-only mode ──
    if args.upload:
        import json
        video_path = args.upload
        if not os.path.isfile(video_path):
            logger.error("Video file not found: %s", video_path)
            sys.exit(1)
        meta_path = os.path.join("output", "latest_metadata.json")
        if not os.path.isfile(meta_path):
            logger.error("Metadata file not found: %s", meta_path)
            sys.exit(1)
        with open(meta_path) as f:
            metadata = json.load(f)
        video_id = step_upload(video_path, metadata)
        if video_id:
            _print_complete(video_id, metadata)
        else:
            logger.error("Upload failed again. Try again later.")
        return

    # Resolve topic
    topic = args.topic
    if not topic:
        if args.auto:
            from topics import get_next_topic
            topic = get_next_topic()
            logger.info("Auto-selected topic: %s", topic)
        else:
            topic = input("💡  Enter video topic: ").strip()
            if not topic:
                logger.error("No topic provided. Exiting.")
                sys.exit(1)

    # Run the appropriate pipeline
    if args.auto:
        run_full_auto_pipeline(topic)
    else:
        run_pipeline(topic, video_path=args.video)


if __name__ == "__main__":
    main()
