"""
scene_planner.py — Intelligent script-to-scene decomposition.

Analyses a video script and breaks it into logical visual scenes, each with:
  • A scene label (intro / body-N / conclusion)
  • The raw text for that section
  • A word count and estimated duration (seconds)
  • 2–3 unique Pexels search queries tailored to the scene content
  • A visual style hint (cinematic, documentary, modern, minimal, aerial)

This replaces the old "generate N generic queries" approach and ensures
every stock footage clip is semantically matched to the words being spoken.

100 % additive — the old pipeline still works unchanged if you call
``stock_footage.download_clips_for_topic()`` directly.

Usage:
    from scene_planner import plan_scenes

    scenes = plan_scenes(script_text, topic="5 Habits of Wealthy People")
    # → [ ScenePlan(label="intro", text="...", queries=["..."], ...), ... ]
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from dataclasses import dataclass, field

logger = logging.getLogger("tubevo.scene_planner")

# ── Visual style rotation ────────────────────────────────────────────
VISUAL_STYLES = [
    "cinematic",       # warm tones, shallow DOF, dramatic lighting
    "documentary",     # handheld, natural lighting, real-world footage
    "modern",          # clean, minimal, tech-forward aesthetics
    "minimal",         # muted colors, lots of negative space
    "aerial",          # drone / bird's-eye establishing shots
]

# Average speaking rate (words per minute) for duration estimation
WORDS_PER_MINUTE = 155


@dataclass
class ScenePlan:
    """A single visual scene in the video."""
    label: str                       # e.g. "intro", "body-1", "conclusion"
    text: str                        # raw script text for this scene
    word_count: int = 0
    estimated_duration: float = 0.0  # seconds
    queries: list[str] = field(default_factory=list)     # 2-3 Pexels search queries
    style: str = "cinematic"         # visual style hint
    clip_count: int = 1              # how many clips to download for this scene


def _estimate_duration(word_count: int) -> float:
    """Estimate speaking duration in seconds from word count."""
    return (word_count / WORDS_PER_MINUTE) * 60.0


def _choose_style(index: int, seed: str = "") -> str:
    """Deterministically-but-variably choose a visual style.
    
    Uses the scene index + an optional seed (e.g. topic hash) so
    consecutive generations of the same topic get different styles.
    """
    rng = random.Random(f"{seed}-{index}")
    return rng.choice(VISUAL_STYLES)


def _split_script_into_sections(script: str) -> list[dict]:
    """Heuristically split a script into intro / body sections / conclusion.
    
    Strategy:
      1. Try to detect numbered sections ("Number one:", "1.", "First,")
      2. Fall back to paragraph-based splitting
      3. Always separate first ~2 sentences as "intro" and last ~2 as "conclusion"
    """
    # Normalise whitespace
    script = script.strip()
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', script)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) < 4:
        # Very short script — treat as single body section
        return [{"label": "body-1", "text": script, "sentences": sentences}]
    
    sections: list[dict] = []
    
    # --- Detect numbered points (e.g. "Number one:", "1.", "First,") ---
    numbered_pattern = re.compile(
        r'^(?:'
        r'(?:Number\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten)'
        r'|(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)'
        r'|\d+[\.\):]'
        r'|(?:Step|Tip|Habit|Rule|Lesson|Point|Reason)\s+\d+'
        r')',
        re.IGNORECASE
    )
    
    # Find indices of numbered sentences
    numbered_indices = [
        i for i, s in enumerate(sentences)
        if numbered_pattern.match(s.strip())
    ]
    
    # --- Build sections ---
    # Intro: sentences before the first numbered point (or first 2 sentences)
    intro_end = numbered_indices[0] if numbered_indices else min(2, len(sentences) - 2)
    intro_end = max(1, intro_end)  # at least 1 sentence
    
    intro_sentences = sentences[:intro_end]
    sections.append({
        "label": "intro",
        "text": " ".join(intro_sentences),
        "sentences": intro_sentences,
    })
    
    if numbered_indices and len(numbered_indices) >= 2:
        # Split body by numbered points
        end_idx = None  # Ensure end_idx is always defined
        for idx_pos, start_idx in enumerate(numbered_indices):
            if idx_pos + 1 < len(numbered_indices):
                end_idx = numbered_indices[idx_pos + 1]
            else:
                # Last numbered section — extend to near the end, leaving room for conclusion
                end_idx = max(start_idx + 1, len(sentences) - 2)
            
            body_sentences = sentences[start_idx:end_idx]
            if body_sentences:
                sections.append({
                    "label": f"body-{idx_pos + 1}",
                    "text": " ".join(body_sentences),
                    "sentences": body_sentences,
                })
        
        # Conclusion: remaining sentences after last body section
        if end_idx is not None:
            last_body_end = end_idx
            if last_body_end < len(sentences):
                conclusion_sentences = sentences[last_body_end:]
                if conclusion_sentences:
                    sections.append({
                        "label": "conclusion",
                        "text": " ".join(conclusion_sentences),
                        "sentences": conclusion_sentences,
                    })
    else:
        # No clear numbered structure — split body evenly into 3-5 chunks
        body_sentences = sentences[intro_end:-2] if len(sentences) > 4 else sentences[intro_end:]
        conclusion_sentences = sentences[-2:] if len(sentences) > 4 else []
        
        # Split body into roughly equal chunks
        chunk_count = min(5, max(2, len(body_sentences) // 3))
        chunk_size = max(1, len(body_sentences) // chunk_count)
        
        for i in range(chunk_count):
            start = i * chunk_size
            end = start + chunk_size if i < chunk_count - 1 else len(body_sentences)
            chunk = body_sentences[start:end]
            if chunk:
                sections.append({
                    "label": f"body-{i + 1}",
                    "text": " ".join(chunk),
                    "sentences": chunk,
                })
        
        if conclusion_sentences:
            sections.append({
                "label": "conclusion",
                "text": " ".join(conclusion_sentences),
                "sentences": conclusion_sentences,
            })
    
    return sections


def _generate_queries_with_ai(
    sections: list[dict],
    topic: str,
    openai_api_key: str | None = None,
) -> list[dict]:
    """Use GPT-4o to generate scene-specific Pexels search queries.
    
    Returns the sections list with ``queries`` added to each.
    Falls back to keyword extraction if OpenAI is unavailable.
    """
    try:
        from openai import OpenAI
        import config
        
        api_key = openai_api_key or config.OPENAI_API_KEY
        if not api_key:
            raise ValueError("No OpenAI API key")
        
        client = OpenAI(api_key=api_key)
        
        # Build a compact representation of sections for the prompt
        section_summaries = []
        for s in sections:
            section_summaries.append({
                "label": s["label"],
                "text": s["text"][:300],  # truncate to save tokens
            })
        
        # Use a random seed to prevent identical queries across generations
        seed_note = f"Randomization seed: {random.randint(1000, 9999)}"
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate Pexels stock video search queries for a YouTube video.\n\n"
                        "RULES:\n"
                        "- For each scene section, generate exactly 2-3 short (2-4 word) search queries\n"
                        "- Queries must be SPECIFIC to that scene's content — not generic\n"
                        "- NO duplicate queries across ANY sections\n"
                        "- Mix of: concrete subjects (e.g. 'person saving money'), "
                        "abstract/mood shots (e.g. 'sunrise golden hour'), "
                        "and lifestyle B-roll (e.g. 'cooking healthy meal')\n"
                        "- Queries should find VIDEOS, not images — prefer action-oriented terms\n"
                        "- Do NOT use the exact topic title as a query\n"
                        f"- {seed_note}\n\n"
                        "Return ONLY a JSON array of objects with keys: label, queries\n"
                        "Example: [{\"label\": \"intro\", \"queries\": [\"city skyline morning\", \"person waking up\"]}]"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"VIDEO TOPIC: {topic}\n\n"
                        f"SCENES:\n{json.dumps(section_summaries, indent=2)}"
                    ),
                },
            ],
            max_tokens=500,
            temperature=1.0,  # high temperature for variety
        )
        
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]
        
        query_data = json.loads(raw)
        
        # Merge AI-generated queries into sections
        query_map = {item["label"]: item["queries"] for item in query_data}
        
        # Deduplication: track all queries globally
        seen_queries: set[str] = set()
        
        for section in sections:
            ai_queries = query_map.get(section["label"], [])
            unique_queries = []
            for q in ai_queries:
                q_lower = q.strip().lower()
                if q_lower not in seen_queries and len(q_lower) > 2:
                    seen_queries.add(q_lower)
                    unique_queries.append(q.strip())
            section["queries"] = unique_queries[:3]  # max 3 per scene
        
        logger.info("AI-generated scene queries: %s",
                     {s["label"]: s.get("queries", []) for s in sections})
        return sections
        
    except Exception as e:
        logger.warning("AI query generation failed, using keyword fallback: %s", e)
        return _generate_queries_fallback(sections, topic)


def _generate_queries_fallback(sections: list[dict], topic: str) -> list[dict]:
    """Fallback: extract keywords from each section to build queries."""
    
    # Common stop words to skip
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "up", "about", "into", "through", "during", "before", "after",
        "above", "below", "between", "out", "off", "over", "under",
        "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "each", "every", "both", "few",
        "more", "most", "other", "some", "such", "no", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "don",
        "now", "your", "you", "they", "them", "their", "this", "that",
        "it", "its", "i", "me", "my", "we", "our", "he", "she", "him",
        "her", "his", "who", "what", "which", "but", "and", "or", "if",
        "because", "as", "while", "until", "although", "though",
    }
    
    seen_queries: set[str] = set()
    
    for section in sections:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', section["text"].lower())
        keywords = [w for w in words if w not in stop_words]
        
        # Build 2-word pair queries from adjacent keywords
        queries = []
        unique_keywords = list(dict.fromkeys(keywords))  # preserve order, dedupe
        
        for j in range(0, min(6, len(unique_keywords)), 2):
            if j + 1 < len(unique_keywords):
                q = f"{unique_keywords[j]} {unique_keywords[j+1]}"
            else:
                q = unique_keywords[j]
            
            if q not in seen_queries:
                seen_queries.add(q)
                queries.append(q)
        
        section["queries"] = queries[:3]
    
    return sections


def plan_scenes(
    script: str,
    topic: str,
    *,
    openai_api_key: str | None = None,
    target_total_clips: int = 10,
    style_seed: str | None = None,
) -> list[ScenePlan]:
    """Decompose a script into visual scenes with per-scene search queries.
    
    Parameters
    ----------
    script : str
        The full video script text.
    topic : str
        The video topic (used as context for AI query generation).
    openai_api_key : str | None
        Override OpenAI key (for BYOK). Falls back to config.OPENAI_API_KEY.
    target_total_clips : int
        Target total number of stock clips across all scenes (8-12 recommended).
    style_seed : str | None
        Seed for visual style rotation. Defaults to topic hash.
        
    Returns
    -------
    list[ScenePlan]
        Ordered list of scenes with queries, durations, and style hints.
    """
    if not script or not script.strip():
        logger.warning("Empty script — returning single default scene")
        return [ScenePlan(
            label="body-1",
            text="",
            queries=[topic[:50]],
            clip_count=target_total_clips,
        )]
    
    # ── 1. Split script into logical sections ────────────────────────
    sections = _split_script_into_sections(script)
    logger.info("Detected %d script sections: %s",
                len(sections), [s["label"] for s in sections])
    
    # ── 2. Generate per-scene search queries ─────────────────────────
    sections = _generate_queries_with_ai(sections, topic, openai_api_key)
    
    # ── 3. Compute durations and clip allocation ─────────────────────
    seed = style_seed or hashlib.md5(f"{topic}-{random.randint(0,9999)}".encode()).hexdigest()
    
    total_words = sum(len(s.get("text", "").split()) for s in sections)
    total_words = max(total_words, 1)
    
    scene_plans: list[ScenePlan] = []
    allocated_clips = 0
    
    for i, section in enumerate(sections):
        word_count = len(section.get("text", "").split())
        duration = _estimate_duration(word_count)
        
        # Allocate clips proportionally to word count, min 1 per scene
        weight = word_count / total_words
        clips = max(1, round(weight * target_total_clips))
        
        # Cap at available queries (can't download more clips than queries)
        queries = section.get("queries", [])
        if not queries:
            queries = [topic[:50]]
        
        scene = ScenePlan(
            label=section["label"],
            text=section.get("text", ""),
            word_count=word_count,
            estimated_duration=duration,
            queries=queries,
            style=_choose_style(i, seed),
            clip_count=clips,
        )
        scene_plans.append(scene)
        allocated_clips += clips
    
    # ── 4. Adjust allocation to hit target ───────────────────────────
    # If we over-allocated, trim from the largest scenes
    while allocated_clips > target_total_clips and any(s.clip_count > 1 for s in scene_plans):
        # Find scene with most clips
        biggest = max(scene_plans, key=lambda s: s.clip_count)
        biggest.clip_count -= 1
        allocated_clips -= 1
    
    # If we under-allocated, add to the largest scenes
    while allocated_clips < target_total_clips:
        # Find scene with most words (most visual real estate)
        biggest = max(scene_plans, key=lambda s: s.word_count)
        biggest.clip_count += 1
        allocated_clips += 1
    
    logger.info(
        "Scene plan: %d scenes, %d total clips, styles: %s",
        len(scene_plans),
        sum(s.clip_count for s in scene_plans),
        [s.style for s in scene_plans],
    )
    for sp in scene_plans:
        logger.info(
            "  %s: %d words, %.1fs, %d clips, queries=%s, style=%s",
            sp.label, sp.word_count, sp.estimated_duration,
            sp.clip_count, sp.queries, sp.style,
        )
    
    return scene_plans


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_script = (
        "Want to build wealth fast? Stop wasting money on things you don't need. "
        "Here are five frugal habits that separate the rich from the broke. "
        "Number one: automate your savings. Pay yourself first. Set up a direct "
        "deposit into a high-yield savings account. This removes willpower from the equation. "
        "Number two: cook at home. Restaurants are bleeding you dry. The average American "
        "spends over three hundred dollars a month eating out. That's almost four thousand a year. "
        "Number three: cancel subscriptions you don't use. Go through your bank statement right now. "
        "I guarantee you'll find at least two or three you forgot about. "
        "Number four: buy used when possible. Your ego is not worth the debt. "
        "Cars, furniture, electronics — let someone else eat the depreciation. "
        "Number five: invest the difference. Every dollar saved is a soldier working for you. "
        "Put it in index funds, real estate, or start a side hustle. "
        "If you found value in this, hit that like button and subscribe for more. "
        "Drop a comment with your best money-saving tip. Let's build wealth together."
    )
    
    scenes = plan_scenes(test_script, topic="5 Frugal Habits That Build Wealth Fast")
    for s in scenes:
        print(f"\n{'='*50}")
        print(f"Scene: {s.label} | {s.word_count} words | {s.estimated_duration:.1f}s")
        print(f"Style: {s.style} | Clips: {s.clip_count}")
        print(f"Queries: {s.queries}")
        print(f"Text: {s.text[:120]}...")
