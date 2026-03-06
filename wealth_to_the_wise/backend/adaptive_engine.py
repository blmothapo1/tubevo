"""
adaptive_engine.py — Weighted Adaptive Learning Engine

Deterministic weighted preference logic that learns from content_performance
data to influence future video generation decisions per user.

NO machine learning. Pure weighted scoring with exploration randomness.

Influences:
1. Title style selection (curiosity, direct_benefit, contrarian, question, data_driven)
2. Thumbnail concept selection (bold_curiosity, contrarian_dramatic, clean_authority)
3. Hook intensity (conservative, balanced, aggressive)

Safety rules:
- Minimum 5 data points before adaptation begins (cold-start protection)
- 20% exploration floor — no style is ever fully eliminated
- Small-sample dampening to prevent oscillation
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger("tubevo.adaptive_engine")

# ── Constants ────────────────────────────────────────────────────────

# All known style categories
TITLE_STYLES = ["curiosity", "direct_benefit", "contrarian", "question", "data_driven"]
THUMBNAIL_STYLES = ["bold_curiosity", "contrarian_dramatic", "clean_authority", "ai_cinematic"]

# Minimum data points before adaptation kicks in
MIN_DATA_POINTS = 5

# Exploration floor: every style retains at least this probability share
EXPLORATION_FLOOR = 0.20

# Random jitter range added to weights to prevent deterministic lock-in
JITTER_RANGE = 0.10

# Hook intensity thresholds (avg_view_duration_pct)
HOOK_AGGRESSIVE_THRESHOLD = 35.0   # below → aggressive
HOOK_CONSERVATIVE_THRESHOLD = 55.0  # above → conservative (maintain)


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class StyleWeight:
    """A single style's computed weight."""
    style: str
    avg_score: float       # mean engagement_score for this style
    count: int             # number of data points
    raw_weight: float      # normalized weight before floor/jitter
    final_weight: float    # after floor + jitter applied


@dataclass
class PerformanceProfile:
    """Complete adaptive profile for a user.

    This is the single object consumed by script_generator and thumbnail engine.
    """
    # Title
    title_style_weights: list[StyleWeight] = field(default_factory=list)
    recommended_title_style: str = "curiosity"
    title_style_probabilities: dict[str, float] = field(default_factory=dict)

    # Thumbnail
    thumbnail_style_weights: list[StyleWeight] = field(default_factory=list)
    recommended_thumbnail_style: str = "bold_curiosity"
    thumbnail_style_probabilities: dict[str, float] = field(default_factory=dict)

    # Hook
    avg_retention_pct: float = 0.0
    avg_ctr_pct: float = 0.0
    hook_mode: str = "balanced"  # conservative | balanced | aggressive

    # Meta
    total_data_points: int = 0
    adaptation_active: bool = False  # True only when >= MIN_DATA_POINTS


# ── Core weighting logic ─────────────────────────────────────────────

def _compute_style_weights(
    style_scores: dict[str, list[float]],
    all_styles: list[str],
) -> list[StyleWeight]:
    """Compute normalized weights for each style from raw engagement scores.

    Mathematical model:
    1. For each style, compute avg engagement_score from its data points.
    2. Normalize across all styles so weights sum to 1.0.
    3. Apply exploration floor: each style gets at least EXPLORATION_FLOOR / len(styles).
    4. Add small random jitter (±JITTER_RANGE) to prevent deterministic lock-in.
    5. Re-normalize so final weights sum to 1.0.

    Formula:
        raw_weight_i = avg_score_i / sum(avg_score_j for all j)
        floor_i = max(raw_weight_i, EXPLORATION_FLOOR / N)
        jittered_i = floor_i + uniform(-JITTER_RANGE, +JITTER_RANGE)
        final_weight_i = jittered_i / sum(jittered_j for all j)
    """
    n = len(all_styles)
    per_style_floor = EXPLORATION_FLOOR / n

    # Step 1: compute averages
    avg_scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for style in all_styles:
        scores = style_scores.get(style, [])
        counts[style] = len(scores)
        if scores:
            avg_scores[style] = sum(scores) / len(scores)
        else:
            # No data → neutral score (50 out of 100)
            avg_scores[style] = 50.0

    # Step 2: normalize raw weights
    total_avg = sum(avg_scores.values())
    if total_avg == 0:
        total_avg = 1.0  # avoid division by zero
    raw_weights = {s: avg_scores[s] / total_avg for s in all_styles}

    # Step 3: apply exploration floor
    floored = {s: max(raw_weights[s], per_style_floor) for s in all_styles}

    # Step 4: add jitter
    jittered = {
        s: max(0.01, floored[s] + random.uniform(-JITTER_RANGE, JITTER_RANGE))
        for s in all_styles
    }

    # Step 5: re-normalize
    total_jittered = sum(jittered.values())
    final_weights = {s: jittered[s] / total_jittered for s in all_styles}

    # Build result objects
    results = []
    for style in all_styles:
        results.append(StyleWeight(
            style=style,
            avg_score=avg_scores[style],
            count=counts[style],
            raw_weight=raw_weights[style],
            final_weight=final_weights[style],
        ))

    return results


def _pick_weighted_style(weights: list[StyleWeight]) -> str:
    """Select a style using weighted random choice.

    Uses the final_weight as probability for random.choices().
    This ensures high-performing styles are picked more often,
    but exploration floor prevents any style from dying.
    """
    styles = [w.style for w in weights]
    probs = [w.final_weight for w in weights]
    chosen = random.choices(styles, weights=probs, k=1)[0]
    return chosen


def _determine_hook_mode(avg_retention_pct: float, total_points: int) -> str:
    """Determine hook intensity based on average view duration.

    - avg_view_duration_pct < 35% → aggressive (viewers leave early)
    - avg_view_duration_pct > 55% → conservative (retention is strong)
    - In between → balanced

    With < MIN_DATA_POINTS, always returns 'balanced'.
    """
    if total_points < MIN_DATA_POINTS:
        return "balanced"

    if avg_retention_pct < HOOK_AGGRESSIVE_THRESHOLD:
        return "aggressive"
    elif avg_retention_pct > HOOK_CONSERVATIVE_THRESHOLD:
        return "conservative"
    else:
        return "balanced"


# ── Main public API ──────────────────────────────────────────────────

def get_user_performance_profile(
    performance_rows: list[dict],
) -> PerformanceProfile:
    """Build a complete adaptive profile from raw content_performance rows.

    Parameters
    ----------
    performance_rows : list[dict]
        Each dict must have keys:
        - title_style_used: str | None
        - thumbnail_concept_used: str | None
        - engagement_score: int
        - ctr_pct: str | None  (e.g. "4.2")
        - avg_view_duration_pct: str | None  (e.g. "42.5")

    Returns
    -------
    PerformanceProfile
        Complete adaptive profile ready for consumption by generators.
    """
    profile = PerformanceProfile()
    profile.total_data_points = len(performance_rows)

    if not performance_rows:
        # Cold start — uniform weights
        profile.title_style_weights = _compute_style_weights({}, TITLE_STYLES)
        profile.thumbnail_style_weights = _compute_style_weights({}, THUMBNAIL_STYLES)
        profile.recommended_title_style = _pick_weighted_style(profile.title_style_weights)
        profile.recommended_thumbnail_style = _pick_weighted_style(profile.thumbnail_style_weights)
        profile.title_style_probabilities = {w.style: w.final_weight for w in profile.title_style_weights}
        profile.thumbnail_style_probabilities = {w.style: w.final_weight for w in profile.thumbnail_style_weights}
        profile.hook_mode = "balanced"
        logger.info("Adaptive profile: cold start (0 data points), uniform weights")
        return profile

    # ── Gather per-style engagement scores ───────────────────────────
    title_scores: dict[str, list[float]] = {s: [] for s in TITLE_STYLES}
    thumb_scores: dict[str, list[float]] = {s: [] for s in THUMBNAIL_STYLES}
    ctr_values: list[float] = []
    retention_values: list[float] = []

    for row in performance_rows:
        score = row.get("engagement_score", 0)

        # Title style
        ts = row.get("title_style_used")
        if ts and ts in title_scores:
            title_scores[ts].append(float(score))

        # Thumbnail style
        tc = row.get("thumbnail_concept_used")
        if tc and tc in thumb_scores:
            thumb_scores[tc].append(float(score))

        # CTR
        ctr_raw = row.get("ctr_pct")
        if ctr_raw:
            try:
                ctr_values.append(float(ctr_raw))
            except (ValueError, TypeError):
                pass

        # Retention
        ret_raw = row.get("avg_view_duration_pct")
        if ret_raw:
            try:
                retention_values.append(float(ret_raw))
            except (ValueError, TypeError):
                pass

    # ── Compute weights ──────────────────────────────────────────────
    adaptation_active = len(performance_rows) >= MIN_DATA_POINTS
    profile.adaptation_active = adaptation_active

    if adaptation_active:
        profile.title_style_weights = _compute_style_weights(title_scores, TITLE_STYLES)
        profile.thumbnail_style_weights = _compute_style_weights(thumb_scores, THUMBNAIL_STYLES)
    else:
        # Not enough data — use uniform weights (cold start behavior)
        profile.title_style_weights = _compute_style_weights({}, TITLE_STYLES)
        profile.thumbnail_style_weights = _compute_style_weights({}, THUMBNAIL_STYLES)
        logger.info("Adaptive profile: %d data points < %d minimum, using uniform weights",
                     len(performance_rows), MIN_DATA_POINTS)

    profile.recommended_title_style = _pick_weighted_style(profile.title_style_weights)
    profile.recommended_thumbnail_style = _pick_weighted_style(profile.thumbnail_style_weights)
    profile.title_style_probabilities = {w.style: w.final_weight for w in profile.title_style_weights}
    profile.thumbnail_style_probabilities = {w.style: w.final_weight for w in profile.thumbnail_style_weights}

    # ── Aggregated metrics ───────────────────────────────────────────
    profile.avg_ctr_pct = sum(ctr_values) / len(ctr_values) if ctr_values else 0.0
    profile.avg_retention_pct = sum(retention_values) / len(retention_values) if retention_values else 0.0

    # ── Hook mode ────────────────────────────────────────────────────
    profile.hook_mode = _determine_hook_mode(profile.avg_retention_pct, len(performance_rows))

    logger.info(
        "Adaptive profile: %d points, active=%s, title=%s (p=%.2f), thumb=%s (p=%.2f), "
        "hook=%s, retention=%.1f%%, ctr=%.1f%%",
        profile.total_data_points, profile.adaptation_active,
        profile.recommended_title_style,
        profile.title_style_probabilities.get(profile.recommended_title_style, 0),
        profile.recommended_thumbnail_style,
        profile.thumbnail_style_probabilities.get(profile.recommended_thumbnail_style, 0),
        profile.hook_mode,
        profile.avg_retention_pct, profile.avg_ctr_pct,
    )

    return profile


def profile_to_dict(profile: PerformanceProfile) -> dict:
    """Serialize a PerformanceProfile to a plain dict for pipeline injection."""
    return {
        "recommended_title_style": profile.recommended_title_style,
        "title_style_probabilities": profile.title_style_probabilities,
        "recommended_thumbnail_style": profile.recommended_thumbnail_style,
        "thumbnail_style_probabilities": profile.thumbnail_style_probabilities,
        "hook_mode": profile.hook_mode,
        "avg_retention_pct": profile.avg_retention_pct,
        "avg_ctr_pct": profile.avg_ctr_pct,
        "total_data_points": profile.total_data_points,
        "adaptation_active": profile.adaptation_active,
    }
