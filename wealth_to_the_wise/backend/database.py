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


# ── Engine + session factory ─────────────────────────────────────────

_db_url = _resolve_database_url(get_settings().database_url)
_using_sqlite = _is_sqlite(_db_url)

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

async def _run_migrations(conn) -> None:
    """Add missing columns to existing tables.

    ``Base.metadata.create_all`` only creates *new* tables — it won't add
    columns that were added to the ORM models after the table was first
    created.  This function uses ``ALTER TABLE … ADD COLUMN IF NOT EXISTS``
    (PostgreSQL 9.6+) to patch the schema forward without data loss.

    For SQLite (dev only) we use a try/except approach since SQLite
    doesn't support ``IF NOT EXISTS`` on ``ADD COLUMN``.
    """
    from sqlalchemy import text

    is_pg = not _using_sqlite

    # (table, column, type[, default])
    migrations: list[tuple[str, str, str]] = [
        # User model additions
        ("users", "stripe_customer_id", "VARCHAR(64)"),
        ("users", "reset_token", "VARCHAR(64)"),
        ("users", "reset_token_expires", "TIMESTAMPTZ"),
        # Phase 6 — pipeline progress tracking
        ("video_records", "progress_step", "VARCHAR(100)"),
        ("video_records", "progress_pct", "INTEGER DEFAULT 0"),
        # Phase 5 — SRT path on video records
        ("video_records", "srt_path", "TEXT"),
        # Phase 4 & 5 — video production preferences on user_api_keys
        ("user_api_keys", "subtitle_style", "VARCHAR(30) DEFAULT 'bold_pop'"),
        ("user_api_keys", "burn_captions", "BOOLEAN DEFAULT TRUE"),
        ("user_api_keys", "speech_speed", "VARCHAR(10)"),
        # Beta user flag
        ("users", "is_beta", "BOOLEAN DEFAULT FALSE"),
        # Adaptive learning — new columns on content_performance
        ("content_performance", "title_style_used", "VARCHAR(30)"),
        ("content_performance", "hook_mode_used", "VARCHAR(20)"),
    ]

    for table, column, col_type in migrations:
        if is_pg:
            stmt = text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            )
            await conn.execute(stmt)
            logger.info("Migration: ensured %s.%s exists", table, column)
        else:
            # SQLite: no IF NOT EXISTS — just catch the "duplicate column" error
            try:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                )
                logger.info("Migration: added %s.%s", table, column)
            except Exception:
                pass  # column already exists

    # Add unique index on stripe_customer_id if it doesn't exist (PostgreSQL)
    if is_pg:
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_stripe_customer_id "
            "ON users (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
        ))
        logger.info("Migration: ensured ix_users_stripe_customer_id index exists")


async def create_tables() -> None:
    """Create all tables that don't exist yet, then run column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
    logger.info("Database tables verified / created / migrated.")


async def dispose_engine() -> None:
    """Cleanly close the connection pool on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")
