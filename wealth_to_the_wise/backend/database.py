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


async def create_tables() -> None:
    """Create all tables that don't exist yet, then run Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_alembic_upgrade()
    logger.info("Database tables verified / created / migrated.")


async def dispose_engine() -> None:
    """Cleanly close the connection pool on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")
