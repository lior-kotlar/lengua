"""Alembic migration environment (async), targeting the app's ``Base.metadata`` (task 1.4.1).

The database URL is resolved at runtime (never hard-coded in ``alembic.ini``) so the same
migrations run against local Supabase, CI, staging, and prod. Precedence (see
:func:`app.db.migration_url.resolve_migration_url`):

1. ``alembic -x db_url=postgresql://… upgrade head`` (an explicit per-invocation override —
   used by the schema round-trip tests against a throwaway database), else
2. ``alembic -x env=staging|prod|local`` → ``STAGING_DATABASE_URL`` / ``PROD_DATABASE_URL`` /
   ``DATABASE_URL`` (the CD migrate jobs use this so each env reads its own secret), else
3. ``DATABASE_URL`` from :func:`app.settings.get_settings`.

The URL is rewritten to the ``postgresql+asyncpg://`` driver via :func:`app.db.session.async_dsn`
and migrations run through an async engine, matching the application's async persistence layer.

``target_metadata`` is :data:`app.db.base.Base.metadata`; importing :mod:`app.db.models` here
registers every ORM model on it so ``--autogenerate`` and the metadata-backed tests see the full
schema.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.db.models  # noqa: F401 — registers all ORM models on Base.metadata
from app.db.base import Base
from app.db.migration_url import resolve_migration_url
from app.db.session import async_dsn
from app.settings import get_settings

# Alembic Config object (reads alembic.ini).
config = context.config

# Configure Python logging from the ini file, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic compares against for --autogenerate.
target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the migration target URL (``-x db_url=`` > ``-x env=`` > ``DATABASE_URL``).

    Precedence + per-env mapping live in :func:`app.db.migration_url.resolve_migration_url`; the
    result is rewritten to SQLAlchemy's ``postgresql+asyncpg`` driver scheme.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    url = resolve_migration_url(x_args, os.environ, get_settings().database_url)
    return async_dsn(url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL against a URL, no live connection)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Configure the context for a live connection and run the migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Create an async engine, run the migrations over one connection, then dispose it."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # one-shot connection; nothing lingers to block DROP DATABASE
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode through the async engine."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
