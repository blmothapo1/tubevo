"""
topics.py — Rotating topic bank for Wealth to the Wise.

The pipeline picks the next unused topic automatically.
Add as many topics as you want — they're used in order,
and a pointer file tracks where you left off.
"""

from __future__ import annotations

import json
from pathlib import Path

# ── Topic bank ──────────────────────────────────────────────────────
# Add / remove / reorder freely. The pipeline works through them top-to-bottom.

TOPICS: list[str] = [
    "5 Frugal Habits That Build Wealth Fast",
    "Why Broke People Stay Broke — And How to Fix It",
    "The 50/30/20 Budget Rule Explained in 3 Minutes",
    "How to Save $10,000 in 6 Months on Any Income",
    "7 Money Mistakes Keeping You Poor",
    "Compound Interest: The 8th Wonder of the World",
    "How to Start Investing With Just $100",
    "Side Hustles That Actually Pay — No Fluff",
    "The Latte Factor: Small Leaks Sink Big Ships",
    "How the Rich Think Differently About Money",
    "Emergency Fund 101: Why You Need One Now",
    "Debt Snowball vs Debt Avalanche — Which Wins?",
    "How to Negotiate Your Salary Like a Pro",
    "5 Books That Changed My Financial Life",
    "Why You Should Pay Yourself First — Every Time",
    "Credit Score Secrets Nobody Tells You",
    "How to Live Below Your Means Without Feeling Poor",
    "Index Funds for Beginners — The Lazy Path to Wealth",
    "The Real Cost of Subscriptions You Forgot About",
    "Financial Freedom by 40: A Realistic Blueprint",
    "How to Stop Impulse Buying for Good",
    "Passive Income Ideas That Actually Work in 2026",
    "Why Cash is Trash — And What to Hold Instead",
    "How to Teach Your Kids About Money Early",
    "Retirement Planning in Your 20s: Start Now or Regret Later",
    "The Psychology of Spending — Why You Buy What You Don't Need",
    "How to Build Multiple Streams of Income",
    "Renting vs Buying a Home — The Math Nobody Shows You",
    "Tax Hacks Every Worker Should Know",
    "The Minimalist Money Mindset — Less Stuff, More Wealth",
]

# ── Pointer tracking ────────────────────────────────────────────────
_POINTER_FILE = Path("output") / ".topic_pointer.json"


def _read_pointer() -> int:
    """Return the current index into TOPICS (0-based)."""
    if _POINTER_FILE.exists():
        data = json.loads(_POINTER_FILE.read_text())
        return data.get("index", 0)
    return 0


def _write_pointer(index: int) -> None:
    _POINTER_FILE.parent.mkdir(exist_ok=True)
    _POINTER_FILE.write_text(json.dumps({"index": index}))


def get_next_topic() -> str:
    """Return the next topic in the bank and advance the pointer.
    Wraps around when all topics have been used."""
    idx = _read_pointer()
    topic = TOPICS[idx % len(TOPICS)]
    _write_pointer((idx + 1) % len(TOPICS))
    return topic


def peek_next_topic() -> str:
    """Return the next topic WITHOUT advancing the pointer."""
    idx = _read_pointer()
    return TOPICS[idx % len(TOPICS)]


# ── CLI helper ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"📋  {len(TOPICS)} topics in the bank")
    print(f"👉  Next up: {peek_next_topic()}")
