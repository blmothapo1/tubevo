#!/usr/bin/env python3
"""
One-off migration script: run with `railway run -- python run_migrations.py`

Applies the ALTER TABLE statements that Alembic migrations 0003 and 0005
would have done.  Uses psycopg2 (sync driver) so there's no asyncio issue.

Safe to run multiple times — every statement is wrapped in IF NOT EXISTS /
column existence checks.
"""

from __future__ import annotations

import os
import sys


def get_sync_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("ERROR: DATABASE_URL not set. Run this via `railway run`.")
        sys.exit(1)
    # Normalise to plain postgresql:// for psycopg2
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    if "+asyncpg" in raw:
        raw = raw.replace("+asyncpg", "", 1)
    return raw


def column_exists(conn, table: str, column: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def main() -> None:
    from sqlalchemy import create_engine, text

    url = get_sync_url()
    print(f"Connecting to: {url[:30]}...")
    engine = create_engine(url)

    with engine.begin() as conn:
        # --- Migration 0003: add feature_overrides_json to users ---
        if not column_exists(conn, "users", "feature_overrides_json"):
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN feature_overrides_json TEXT"
            ))
            print("✅ Added users.feature_overrides_json")
        else:
            print("⏭️  users.feature_overrides_json already exists")

        # --- Migration 0005: add channel_id FK to existing tables ---
        tables_with_index = [
            "video_records",
            "posting_schedules",
            "content_memory",
            "content_performance",
        ]
        tables_without_index = ["user_preferences"]

        for table in tables_with_index + tables_without_index:
            if not column_exists(conn, table, "channel_id"):
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN channel_id VARCHAR(36) "
                    f"REFERENCES channels(id)"
                ))
                print(f"✅ Added {table}.channel_id")
            else:
                print(f"⏭️  {table}.channel_id already exists")

        # Indexes
        for table in tables_with_index:
            idx_name = f"ix_{table}_channel_id"
            exists = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
            ), {"idx": idx_name}).fetchone()
            if not exists:
                conn.execute(text(
                    f"CREATE INDEX {idx_name} ON {table} (channel_id)"
                ))
                print(f"✅ Created index {idx_name}")
            else:
                print(f"⏭️  Index {idx_name} already exists")

    engine.dispose()
    print("\n🎉 All migrations applied successfully!")


if __name__ == "__main__":
    main()
