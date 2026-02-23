"""
scheduler.py — Run the full pipeline on a recurring schedule.

Usage:
    # Run once now:
    python scheduler.py --now

    # Start the scheduler (runs every day at 9 AM by default):
    python scheduler.py

    # Custom schedule:
    python scheduler.py --time 14:00          # daily at 2 PM
    python scheduler.py --every monday --time 09:00   # weekly on Monday
"""

from __future__ import annotations

import argparse
import logging
import time

import schedule

import config  # noqa: F401  (ensures logging is configured)
from topics import get_next_topic

logger = logging.getLogger("wealth_to_the_wise.scheduler")


def _run_full_pipeline() -> None:
    """Pick the next topic and run the entire hands-free pipeline."""
    # Import here to avoid circular imports
    from main import run_full_auto_pipeline

    topic = get_next_topic()
    logger.info("Scheduler triggered — Topic: %s", topic)
    try:
        run_full_auto_pipeline(topic)
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)


def start_scheduler(run_time: str = "09:00", day: str | None = None) -> None:
    """Start the scheduler loop.

    Parameters
    ----------
    run_time : str
        Time of day in HH:MM format (24-hour).
    day : str | None
        Day of week (e.g. "monday"). If None, runs daily.
    """
    if day:
        job = getattr(schedule.every(), day.lower())
        job.at(run_time).do(_run_full_pipeline)
        logger.info("Scheduled: every %s at %s", day.capitalize(), run_time)
    else:
        schedule.every().day.at(run_time).do(_run_full_pipeline)
        logger.info("Scheduled: every day at %s", run_time)

    logger.info("Scheduler running. Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wealth to the Wise — Scheduler")
    parser.add_argument("--now", action="store_true", help="Run one pipeline immediately and exit")
    parser.add_argument("--time", default="09:00", help="Time to run daily (HH:MM, default 09:00)")
    parser.add_argument("--every", default=None, help="Day of week (e.g. monday). Omit for daily.")
    args = parser.parse_args()

    if args.now:
        _run_full_pipeline()
    else:
        start_scheduler(run_time=args.time, day=args.every)


if __name__ == "__main__":
    main()
