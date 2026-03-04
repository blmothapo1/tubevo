"""
Alembic env.py — wired to the Tubevo async SQLAlchemy engine.

Supports both:
  • ``alembic upgrade head``    — offline SQL generation (rare, for DBA review)
  • ``alembic upgrade head``    — online execution via the existing async engine
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the declarative Base so Alembic can auto-detect model changes.
from backend.database import Base  # noqa: F401  — side-effect: registers all models
from backend.models import *  # noqa: F401,F403  — ensure every model is imported
from backend.config import get_settings

# Alembic Config object — gives access to values in alembic.ini.
config = context.config

# Set up Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object for 'autogenerate' support.
target_metadata = Base.metadata


def _get_url() -> str:
    """Resolve the async database URL from application settings."""
    raw = get_settings().database_url
    # Normalise for SQLAlchemy async drivers
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database.

    Calls ``context.execute()`` with literal SQL strings.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure the Alembic context with a live connection and run."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations in an async context."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live database (normal mode)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
