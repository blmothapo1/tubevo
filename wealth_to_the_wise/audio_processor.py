"""
audio_processor.py — Post-process voiceover audio for premium quality.

Phase 4 — Audio Polish.

Pipeline:
  1. Trim silence from beginning/end
  2. Normalize loudness to broadcast standard (-14 LUFS)
  3. Generate subtle ambient background music (royalty-free synthesis)
  4. Mix voice + music with ducking (voice priority)
  5. Output polished audio file

All processing uses FFmpeg CLI subprocesses — zero extra Python RAM.

Usage:
    from audio_processor import polish_audio

    polished_path = polish_audio("output/voiceover.mp3")
    # → "output/voiceover_polished.mp3"
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("tubevo.audio_processor")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Constants ────────────────────────────────────────────────────────
TARGET_LUFS = -14.0           # Broadcast-standard loudness
TARGET_TP = -1.0              # True peak ceiling (dBTP)
MUSIC_VOLUME_DB = -26.0       # Background music volume (barely noticeable)
DUCK_THRESHOLD_DB = -30.0     # Ducking trigger threshold
DUCK_RATIO = 6                # Ducking compression ratio
DUCK_ATTACK_MS = 80           # How fast the ducking kicks in
DUCK_RELEASE_MS = 600         # How slowly music comes back after voice stops
SILENCE_THRESHOLD_DB = -40    # Silence detection threshold
SILENCE_MIN_DURATION = 0.3    # Min silence duration to trim (seconds)


# ── Helpers ──────────────────────────────────────────────────────────

def _run_ffmpeg(args: list[str], description: str = "ffmpeg") -> str:
    """Run an FFmpeg command, return stderr (useful for loudnorm analysis)."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "info"] + args
    logger.info("Audio: %s …", description)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error("%s stderr: %s", description, result.stderr[-2000:] if result.stderr else "(none)")
        raise RuntimeError(f"{description} failed (exit {result.returncode}): {result.stderr[-500:]}")
    return result.stderr or ""


def _run_ffprobe(path: str) -> dict:
    """Probe a media file and return the JSON output."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}")
    return json.loads(result.stdout)


def _get_duration(path: str) -> float:
    """Get audio duration in seconds."""
    info = _run_ffprobe(path)
    return float(info["format"]["duration"])


# ── Step 1: Trim silence ────────────────────────────────────────────

def trim_silence(input_path: str, output_path: str) -> str:
    """Remove silence from the beginning and end of an audio file.

    Uses FFmpeg's silenceremove filter:
    - First pass: remove leading silence
    - Second pass: remove trailing silence (via areverse trick)
    """
    _run_ffmpeg([
        "-i", input_path,
        "-af", (
            # Remove leading silence
            f"silenceremove=start_periods=1:start_threshold={SILENCE_THRESHOLD_DB}dB"
            f":start_duration={SILENCE_MIN_DURATION}:start_silence=0.05,"
            # Remove trailing silence (reverse → remove leading → reverse back)
            f"areverse,"
            f"silenceremove=start_periods=1:start_threshold={SILENCE_THRESHOLD_DB}dB"
            f":start_duration={SILENCE_MIN_DURATION}:start_silence=0.05,"
            f"areverse"
        ),
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path,
    ], "trim silence")

    orig_dur = _get_duration(input_path)
    new_dur = _get_duration(output_path)
    trimmed = orig_dur - new_dur
    if trimmed > 0.1:
        logger.info("Trimmed %.1fs of silence (%.1fs → %.1fs)", trimmed, orig_dur, new_dur)
    else:
        logger.info("No significant silence to trim")

    return output_path


# ── Step 2: Normalize loudness ──────────────────────────────────────

def normalize_loudness(input_path: str, output_path: str) -> str:
    """Normalize audio to broadcast standard using EBU R128 loudnorm.

    Two-pass approach for best quality:
    - Pass 1: Measure input loudness statistics
    - Pass 2: Apply correction with measured parameters
    """
    # Pass 1: Measure
    stderr = _run_ffmpeg([
        "-i", input_path,
        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:print_format=json",
        "-f", "null", "/dev/null",
    ], "loudnorm analysis (pass 1)")

    # Parse the loudnorm JSON stats from stderr
    measured = _parse_loudnorm_stats(stderr)

    if measured:
        # Pass 2: Apply with measured parameters
        _run_ffmpeg([
            "-i", input_path,
            "-af", (
                f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11"
                f":measured_I={measured['input_i']}"
                f":measured_TP={measured['input_tp']}"
                f":measured_LRA={measured['input_lra']}"
                f":measured_thresh={measured['input_thresh']}"
                f":linear=true"
            ),
            "-c:a", "libmp3lame", "-q:a", "2",
            "-ar", "44100",
            output_path,
        ], "loudnorm correction (pass 2)")
    else:
        # Fallback: single-pass loudnorm (still good, just not as precise)
        logger.warning("Could not parse loudnorm stats — using single-pass normalization")
        _run_ffmpeg([
            "-i", input_path,
            "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11",
            "-c:a", "libmp3lame", "-q:a", "2",
            "-ar", "44100",
            output_path,
        ], "loudnorm single-pass")

    return output_path


def _parse_loudnorm_stats(stderr: str) -> dict | None:
    """Extract loudnorm measurement JSON from FFmpeg stderr."""
    # FFmpeg outputs the stats as a JSON block in stderr
    try:
        # Find the JSON block — it starts after [Parsed_loudnorm...
        # and looks like { "input_i": "-23.5", ... }
        lines = stderr.split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("{"):
                in_json = True
            if in_json:
                json_lines.append(stripped)
            if in_json and stripped.startswith("}"):
                break

        if json_lines:
            json_str = "\n".join(json_lines)
            data = json.loads(json_str)
            # Validate we have the required keys
            required = ["input_i", "input_tp", "input_lra", "input_thresh"]
            if all(k in data for k in required):
                return data
    except (json.JSONDecodeError, IndexError, KeyError):
        pass

    return None


# ── Step 3: Generate ambient background music ───────────────────────

# ── Chord progressions for mood variety ──────────────────────────────
# Each progression is a list of 4 chords; each chord is (root, third, fifth, octave) in Hz.
# The pipeline cycles through chords over the track duration.
CHORD_PROGRESSIONS: dict[str, list[tuple[float, float, float, float]]] = {
    # I – vi – IV – V in C major (warm, uplifting — default)
    "major_warm": [
        (130.81, 164.81, 196.00, 261.63),   # C  (C-E-G-C)
        (110.00, 130.81, 164.81, 220.00),   # Am (A-C-E-A)
        (174.61, 220.00, 261.63, 349.23),   # F  (F-A-C-F)
        (146.83, 185.00, 220.00, 293.66),   # G  (G-B-D-G)
    ],
    # i – VI – III – VII in A minor (contemplative, serious)
    "minor_reflective": [
        (110.00, 130.81, 164.81, 220.00),   # Am
        (174.61, 220.00, 261.63, 349.23),   # F
        (130.81, 164.81, 196.00, 261.63),   # C
        (196.00, 246.94, 293.66, 392.00),   # G
    ],
    # I – IV – vi – V in G major (hopeful, forward-moving)
    "hopeful": [
        (196.00, 246.94, 293.66, 392.00),   # G
        (130.81, 164.81, 196.00, 261.63),   # C
        (164.81, 196.00, 246.94, 329.63),   # Em
        (146.83, 185.00, 220.00, 293.66),   # D  (approx)
    ],
    # I – V – vi – IV  (universally emotional — "pop" canon)
    "emotional": [
        (130.81, 164.81, 196.00, 261.63),   # C
        (196.00, 246.94, 293.66, 392.00),   # G
        (110.00, 130.81, 164.81, 220.00),   # Am
        (174.61, 220.00, 261.63, 349.23),   # F
    ],
}


def generate_ambient_music(
    duration: float,
    output_path: str,
    *,
    frequencies: list[float] | None = None,
    tremolo_base: float | None = None,
    progression: str | None = None,
) -> str:
    """Generate a subtle ambient pad using FFmpeg's audio synthesis.

    Creates a warm, barely-noticeable ambient background using layered
    sine waves with chord progressions for a richer, more musical feel.
    100% royalty-free since it's generated programmatically.

    Parameters
    ----------
    duration : float
        Length of the ambient track in seconds.
    output_path : str
        Path to write the resulting MP3.
    frequencies : list[float] | None
        Legacy override — static 4-frequency chord (skips progressions).
    tremolo_base : float | None
        Override tremolo speed (Hz).  Default 0.07 for a slow pulse.
    progression : str | None
        Chord progression key from CHORD_PROGRESSIONS.
        One of: ``major_warm``, ``minor_reflective``, ``hopeful``, ``emotional``.
        When *None* and *frequencies* are also *None*, defaults to
        ``major_warm``.
    """
    trem_base = tremolo_base if tremolo_base is not None else 0.07

    # ── Resolve chord list ──
    if frequencies is not None:
        # Legacy / explicit override: single static chord
        chords = [tuple(frequencies[:4])]
    else:
        prog_name = progression or "major_warm"
        chords = CHORD_PROGRESSIONS.get(prog_name, CHORD_PROGRESSIONS["major_warm"])

    logger.info(
        "Generating ambient music: progression=%s (%d chords), tremolo=%.3f, dur=%.1fs",
        progression or ("custom" if frequencies else "major_warm"),
        len(chords),
        trem_base,
        duration,
    )

    # ── Compute chord timing ──
    # Each chord plays for ``chord_dur`` seconds with a 1.5s cross-fade.
    num_chords = len(chords)
    if num_chords == 1:
        # Single static chord — original behaviour
        chord_sections = [(0.0, duration, chords[0])]
    else:
        # Cycle chords evenly across the full duration
        chord_dur = duration / num_chords
        chord_sections = []
        for i in range(num_chords):
            start = i * chord_dur
            chord_sections.append((start, chord_dur, chords[i % num_chords]))

    # ── Build per-chord audio segments then concatenate ──
    import tempfile as _tmpmod
    tmp_dir = _tmpmod.mkdtemp(prefix="tubevo_music_")
    segment_paths: list[str] = []

    try:
        for idx, (start_t, seg_dur, (f1, f2, f3, f4)) in enumerate(chord_sections):
            seg_path = os.path.join(tmp_dir, f"chord_{idx:02d}.wav")

            # Build a 4-voice pad with tremolo + low-pass
            af_filter = (
                # Voice 1: Root — warm and present
                "sine=frequency={f1}:duration={dur},"
                "tremolo=f={t1}:d=0.3,"
                "volume=0.25 [v1];"
                # Voice 2: Third — gives major/minor character
                "sine=frequency={f2}:duration={dur},"
                "tremolo=f={t2}:d=0.25,"
                "volume=0.18 [v2];"
                # Voice 3: Fifth — harmonic anchor
                "sine=frequency={f3}:duration={dur},"
                "tremolo=f={t3}:d=0.2,"
                "volume=0.15 [v3];"
                # Voice 4: Octave — airy top layer
                "sine=frequency={f4}:duration={dur},"
                "tremolo=f={t4}:d=0.35,"
                "volume=0.08 [v4];"
                # Voice 5: Sub-bass an octave below root — warmth
                "sine=frequency={f_sub}:duration={dur},"
                "tremolo=f={t5}:d=0.15,"
                "volume=0.10 [v5];"
                # Mix all voices
                "[v1][v2][v3][v4][v5] amix=inputs=5:duration=longest,"
                # Low-pass for warmth
                "lowpass=f=900:p=2,"
                # Cross-fade friendly: fade-in first 1.5s, fade-out last 1.5s
                "afade=t=in:st=0:d={fade_in},"
                "afade=t=out:st={fade_out_start}:d={fade_out},"
                # Volume
                "volume={vol}dB"
            ).format(
                f1=f1, f2=f2, f3=f3, f4=f4,
                f_sub=f1 / 2,  # sub-bass one octave below root
                t1=round(trem_base + 0.01, 3),
                t2=round(trem_base - 0.01, 3),
                t3=trem_base,
                t4=round(trem_base - 0.02, 3),
                t5=round(trem_base + 0.005, 3),
                dur=seg_dur + 2,  # buffer
                fade_in=min(1.5, seg_dur * 0.15),
                fade_out_start=max(0, seg_dur - min(1.5, seg_dur * 0.15)),
                fade_out=min(1.5, seg_dur * 0.15),
                vol=MUSIC_VOLUME_DB,
            )

            _run_ffmpeg([
                "-f", "lavfi",
                "-i", af_filter,
                "-t", f"{seg_dur:.2f}",
                "-c:a", "pcm_s16le",
                "-ar", "44100", "-ac", "2",
                seg_path,
            ], f"generate chord segment {idx + 1}/{len(chord_sections)}")
            segment_paths.append(seg_path)

        if len(segment_paths) == 1:
            # Single chord — just convert to mp3
            _run_ffmpeg([
                "-i", segment_paths[0],
                "-c:a", "libmp3lame", "-q:a", "4",
                "-ar", "44100", "-ac", "2",
                output_path,
            ], "convert single-chord ambient to mp3")
        else:
            # Concatenate all chord segments with cross-fade
            # Use acrossfade between pairs, or simple concat for reliability
            concat_list = os.path.join(tmp_dir, "concat.txt")
            with open(concat_list, "w") as cl:
                for sp in segment_paths:
                    cl.write(f"file '{sp}'\n")

            _run_ffmpeg([
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                # Overall fade-in/out on the entire track
                "-af", (
                    f"afade=t=in:st=0:d=3,"
                    f"afade=t=out:st={max(0, duration - 3):.2f}:d=3"
                ),
                "-c:a", "libmp3lame", "-q:a", "4",
                "-ar", "44100", "-ac", "2",
                "-t", f"{duration:.2f}",
                output_path,
            ], "concatenate chord segments into ambient track")

        logger.info("Ambient music generated: %s (%.1fs)", output_path, duration)
        return output_path

    finally:
        import shutil as _shutil
        _shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Step 4: Mix with ducking ────────────────────────────────────────

def mix_with_ducking(
    voice_path: str,
    music_path: str,
    output_path: str,
) -> str:
    """Mix voice and background music with sidechain ducking.

    When the narrator speaks, the music volume automatically dips.
    When there's a pause, the music gently rises back.

    Uses FFmpeg's sidechaincompress filter for professional ducking.
    Output is always **stereo 44100 Hz** to prevent left-channel-only
    playback issues from mono voiceover sources.
    """
    _run_ffmpeg([
        "-i", voice_path,
        "-i", music_path,
        "-filter_complex", (
            # Force voice to stereo float planar @ 44100
            "[0:a] aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo [voice];"
            # Force music to stereo float planar @ 44100
            "[1:a] aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo [music];"
            # Apply sidechain compression: voice controls music volume
            f"[music][voice] sidechaincompress="
            f"threshold={DUCK_THRESHOLD_DB}dB:"
            f"ratio={DUCK_RATIO}:"
            f"attack={DUCK_ATTACK_MS}:"
            f"release={DUCK_RELEASE_MS}:"
            f"level_in=1:"
            f"level_sc=1 [ducked_music];"
            # Mix ducked music with voice — use 'first' duration so it ends
            # with the voice track. The finalize step (Step 5) handles the
            # end-of-stream fade-out where the actual duration is known.
            "[voice][ducked_music] amix=inputs=2:duration=first:dropout_transition=0 [mixed];"
            # Final: ensure stereo output (belt-and-suspenders)
            "[mixed] aformat=channel_layouts=stereo [out]"
        ),
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "2",
        "-ar", "44100", "-ac", "2",
        output_path,
    ], "mix voice + music with ducking")

    return output_path


# ── Main entry point ────────────────────────────────────────────────

def polish_audio(
    voice_path: str,
    *,
    output_path: str | None = None,
    add_music: bool = True,
    trim_silence_enabled: bool = True,
    normalize_enabled: bool = True,
    music_frequencies: list[float] | None = None,
    music_tremolo_base: float | None = None,
    music_progression: str | None = None,
) -> str:
    """Full audio polish pipeline: trim → normalize → music → duck → mix.

    Parameters
    ----------
    voice_path : str
        Path to the raw voiceover MP3.
    output_path : str | None
        Where to save. Defaults to ``<voice_path>`` with ``_polished`` suffix.
    add_music : bool
        Whether to add background ambient music (default True).
    trim_silence_enabled : bool
        Whether to trim silence from start/end (default True).
    normalize_enabled : bool
        Whether to normalize loudness (default True).
    music_frequencies : list[float] | None
        Phase 7 — Override ambient pad frequencies for mood rotation.
        When provided, overrides *music_progression* (single static chord).
    music_tremolo_base : float | None
        Phase 7 — Override tremolo speed for mood rotation.
    music_progression : str | None
        Chord progression name (``major_warm``, ``minor_reflective``,
        ``hopeful``, ``emotional``).  Ignored when *music_frequencies*
        is provided.  Default ``major_warm``.

    Returns
    -------
    str
        Path to the polished audio file.
    """
    if output_path is None:
        base, ext = os.path.splitext(voice_path)
        output_path = f"{base}_polished{ext}"

    logger.info("Audio polish pipeline starting: %s", voice_path)

    # Use temp files for intermediate steps
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="tubevo_audio_")

    try:
        current = voice_path

        # ── Step 1: Trim silence ─────────────────────────────────────
        if trim_silence_enabled:
            trimmed_path = os.path.join(tmp_dir, "trimmed.mp3")
            try:
                current = trim_silence(current, trimmed_path)
            except Exception as e:
                logger.warning("Silence trimming failed (non-fatal): %s", e)

        # ── Step 2: Normalize loudness ───────────────────────────────
        if normalize_enabled:
            normalized_path = os.path.join(tmp_dir, "normalized.mp3")
            try:
                current = normalize_loudness(current, normalized_path)
            except Exception as e:
                logger.warning("Loudness normalization failed (non-fatal): %s", e)

        # ── Step 3 & 4: Generate music + mix with ducking ────────────
        if add_music:
            try:
                duration = _get_duration(current)
                music_path = os.path.join(tmp_dir, "ambient_music.mp3")
                generate_ambient_music(
                    duration,
                    music_path,
                    frequencies=music_frequencies,
                    tremolo_base=music_tremolo_base,
                    progression=music_progression,
                )

                mixed_path = os.path.join(tmp_dir, "mixed.mp3")
                current = mix_with_ducking(current, music_path, mixed_path)
            except Exception as e:
                logger.warning("Music mixing failed (non-fatal): %s", e)

        # ── Step 5: Finalize — force stereo + clean fade-out ─────────
        # ElevenLabs outputs mono MP3. If the music step was skipped
        # (add_music=False or error), the audio stays mono and many
        # players route mono to the left channel only.  This step
        # guarantees stereo output and appends a short fade-out at the
        # very end to eliminate codec-boundary glitch artefacts.
        finalized_path = os.path.join(tmp_dir, "finalized.mp3")
        try:
            dur = _get_duration(current)
            fade_start = max(0, dur - 0.15)   # 150 ms fade at the tail
            _run_ffmpeg([
                "-i", current,
                "-af", (
                    # Upmix mono→stereo (no-op if already stereo)
                    "aformat=channel_layouts=stereo,"
                    # Tiny fade-out to kill end-of-stream artefacts
                    f"afade=t=out:st={fade_start:.3f}:d=0.15:curve=tri"
                ),
                "-c:a", "libmp3lame", "-q:a", "2",
                "-ar", "44100", "-ac", "2",
                finalized_path,
            ], "finalize: stereo + fade-out")
            current = finalized_path
        except Exception as e:
            logger.warning("Finalize step failed (non-fatal): %s", e)

        # ── Copy final result to output ──────────────────────────────
        import shutil
        shutil.copy2(current, output_path)

        orig_dur = _get_duration(voice_path)
        final_dur = _get_duration(output_path)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(
            "Audio polish complete: %.1fs → %.1fs (%.1f MB) → %s",
            orig_dur, final_dur, size_mb, output_path,
        )

        return output_path

    finally:
        # Clean up temp files
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_path = str(OUTPUT_DIR / "voiceover.mp3")
    if os.path.isfile(test_path):
        result = polish_audio(test_path)
        logger.info("Done: %s", result)
    else:
        logger.warning("No voiceover.mp3 found. Run voiceover.py first.")
