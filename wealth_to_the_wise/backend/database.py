# filepath: backend/database.py
"""
Async SQLAlchemy database engine and session management.

Uses SQLite (via aiosqlite) for development.  Switch ``DATABASE_URL``
to a PostgreSQL async URL for production.

Railway provides ``DATABASE_URL`` as ``postgresql://…`` — we automatically
rewrite it to ``postgresql+asyncpg://…`` so SQLAlchemy's async engine works.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.database")


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_database_url(raw_url: str) -> str:
    """Normalise the database URL for SQLAlchemy's async engine.

    * ``postgresql://``  →  ``postgresql+asyncpg://``
    * ``postgres://``    →  ``postgresql+asyncpg://``  (Heroku/Railway style)
    * ``sqlite+aiosqlite://`` left as-is
    """
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw_url


def _is_sqlite(url: str) -> bool:
    return "sqlite" in url


def _detect_dialect(url: str) -> str:
    """Return a safe dialect label for logging (never includes credentials)."""
    if "sqlite" in url:
        return "sqlite"
    if "postgres" in url:
        return "postgresql"
    return url.split("://")[0] if "://" in url else "unknown"


def _guard_sqlite_in_production(url: str) -> None:
    """Fail fast if production is running with SQLite.

    SQLite serialises concurrent writes and has no network-level access
    control — it must never be used in a production deployment.

    The guard only triggers when ``ENV`` (or ``APP_ENV``) is **explicitly**
    set to ``"production"``.  This avoids false positives during local
    development (where neither variable is typically set) and in test
    runs (where ``PYTEST_CURRENT_TEST`` is present).
    """
    import os

    # Always allow SQLite when running inside pytest
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.debug("PYTEST_CURRENT_TEST detected — skipping SQLite production guard")
        return

    env = (
        os.environ.get("ENV", "")
        or os.environ.get("APP_ENV", "")
    ).strip().lower()

    is_production = env == "production"
    dialect = _detect_dialect(url)

    logger.info("Database dialect detected: %s (ENV=%r, production=%s)", dialect, env, is_production)

    if is_production and dialect == "sqlite":
        raise RuntimeError(
            "FATAL: SQLite is not allowed in production. "
            "Set DATABASE_URL to a PostgreSQL connection string "
            "(e.g. postgresql://user:pass@host/db) or enable debug mode."
        )


# ── Engine + session factory ─────────────────────────────────────────

_db_url = _resolve_database_url(get_settings().database_url)
_using_sqlite = _is_sqlite(_db_url)

# ── Production guard: block SQLite in production ─────────────────────
_guard_sqlite_in_production(_db_url)

engine = create_async_engine(
    _db_url,
    echo=get_settings().debug,          # SQL logging only in debug mode
    future=True,
    # NullPool for PostgreSQL (Railway) avoids connection-pool issues
    # with serverless-style deployments; SQLite doesn't support pooling.
    **({"poolclass": NullPool} if not _using_sqlite else {}),
)

logger.info("Database engine created: %s", "SQLite" if _using_sqlite else "PostgreSQL")

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base class for all models ────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Dependency: get a DB session per request ─────────────────────────

async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields one session per request."""
    async with async_session_factory() as session:
        try:
            yield session  # type: ignore[misc]
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Startup helper ───────────────────────────────────────────────────

async def _run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` programmatically at startup.

    This replaces the old hand-rolled ALTER TABLE migration list with
    proper Alembic version tracking.  If the DB has never been stamped,
    we stamp the baseline first so only *new* migrations run.

    **Threading note**: Alembic's ``command.*`` functions are synchronous
    and our ``env.py`` uses ``asyncio.run()`` to drive the async engine.
    That fails inside an already-running event loop (FastAPI's lifespan).
    We therefore offload the ENTIRE operation to a worker thread via
    ``asyncio.to_thread`` so it gets its own event loop.
    """
    import asyncio
    import os
    from pathlib import Path

    # Locate alembic.ini relative to this file
    ini_path = str(Path(__file__).resolve().parent.parent / "alembic.ini")
    if not os.path.exists(ini_path):
        logger.warning("alembic.ini not found at %s — skipping migrations", ini_path)
        return

    def _run_in_thread() -> None:
        """Runs in a worker thread — safe to call asyncio.run() here."""
        from alembic import command
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine, inspect

        alembic_cfg = Config(ini_path)

        # Build a plain *synchronous* engine for the stamp/revision check.
        # This avoids any async-in-async issues entirely.
        sync_url = get_settings().database_url
        if sync_url.startswith("postgresql+asyncpg://"):
            sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif sync_url.startswith("sqlite+aiosqlite://"):
            sync_url = sync_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        # Also handle raw Railway-style URLs
        if sync_url.startswith("postgres://"):
            sync_url = sync_url.replace("postgres://", "postgresql://", 1)

        sync_engine = create_engine(sync_url)
        try:
            with sync_engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                current_rev = ctx.get_current_revision()
                if current_rev is None:
                    insp = inspect(conn)
                    tables = insp.get_table_names()
                    if "users" in tables:
                        logger.info(
                            "Existing database detected — stamping Alembic baseline (0001)"
                        )
                        command.stamp(alembic_cfg, "0001")
        finally:
            sync_engine.dispose()

        # Now run pending migrations up to head.
        # This will execute env.py which calls asyncio.run() — that's
        # fine because we're in a plain thread with no running loop.
        logger.info("Running Alembic migrations → head")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations complete.")

    await asyncio.to_thread(_run_in_thread)


async def _apply_column_migrations() -> None:
    """Add columns to existing tables that ``create_all`` can't handle.

    ``Base.metadata.create_all`` creates *new* tables but cannot ALTER
    existing ones.  This helper applies the few ADD COLUMN changes that
    the Empire OS migrations (0003, 0005) require.

    Every statement is guarded by an existence check so it's safe to run
    on every startup — it's a no-op once the columns exist.

    For SQLite (dev/test) the information_schema trick doesn't work, so
    we use ``PRAGMA table_info`` instead.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        if _using_sqlite:
            # SQLite path — use PRAGMA table_info
            async def _col_exists_sqlite(table: str, column: str) -> bool:
                rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
                return any(row[1] == column for row in rows)

            # 0003: feature_overrides_json on users
            if not await _col_exists_sqlite("users", "feature_overrides_json"):
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN feature_overrides_json TEXT"
                ))
                logger.info("Applied migration: users.feature_overrides_json")

            # 0005: channel_id on existing tables
            for table in ["video_records", "posting_schedules", "content_memory",
                          "content_performance", "user_preferences"]:
                if not await _col_exists_sqlite(table, "channel_id"):
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN channel_id VARCHAR(36) "
                        f"REFERENCES channels(id)"
                    ))
                    logger.info("Applied migration: %s.channel_id", table)
        else:
            # PostgreSQL path — use information_schema
            async def _col_exists_pg(table: str, column: str) -> bool:
                result = await conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ), {"t": table, "c": column})
                return result.fetchone() is not None

            # 0003: feature_overrides_json on users
            if not await _col_exists_pg("users", "feature_overrides_json"):
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN feature_overrides_json TEXT"
                ))
                logger.info("Applied migration: users.feature_overrides_json")

            # 0005: channel_id FK on existing tables
            tables_with_index = [
                "video_records", "posting_schedules",
                "content_memory", "content_performance",
            ]
            tables_without_index = ["user_preferences"]

            for table in tables_with_index + tables_without_index:
                if not await _col_exists_pg(table, "channel_id"):
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN channel_id VARCHAR(36) "
                        f"REFERENCES channels(id)"
                    ))
                    logger.info("Applied migration: %s.channel_id", table)

            # Create indexes (PostgreSQL only)
            for table in tables_with_index:
                idx_name = f"ix_{table}_channel_id"
                exists = (await conn.execute(text(
                    "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
                ), {"idx": idx_name})).fetchone()
                if not exists:
                    # CREATE INDEX can't run inside a transaction on some PG
                    # versions, but ALTER TABLE ... ADD ... can. Use plain index.
                    await conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} (channel_id)"
                    ))
                    logger.info("Applied migration: index %s", idx_name)

    logger.info("Column migrations complete.")


async def create_tables() -> None:
    """Create all tables that don't exist yet, then apply column migrations.

    Uses SQLAlchemy's ``create_all`` with ``checkfirst=True`` (the default)
    so only *missing* tables are created — existing ones are left untouched.

    Then runs lightweight ALTER TABLE statements for columns that
    ``create_all`` can't add to pre-existing tables.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _apply_column_migrations()
    logger.info("Database tables verified / created / migrated.")


async def dispose_engine() -> None:
    """Cleanly close the connection pool on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")
