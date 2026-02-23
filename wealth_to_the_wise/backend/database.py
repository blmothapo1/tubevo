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

async def create_tables() -> None:
    """Create all tables that don't exist yet (non-destructive)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")


async def dispose_engine() -> None:
    """Cleanly close the connection pool on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")
