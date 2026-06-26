"""Async SQLAlchemy engine, sessionmaker, and the ``get_db`` dependency (task 1.3.1).

A single async engine (asyncpg driver) and ``async_sessionmaker`` are created lazily from
``DATABASE_URL`` (read via :func:`app.settings.get_settings`) and reused process-wide;
:func:`get_db` is the FastAPI dependency that yields a short-lived :class:`AsyncSession`.

``DATABASE_URL`` is stored in the libpq/psycopg form (``postgresql://…``) — what Supabase, the
test ``conftest``, and ``.env`` all emit — so :func:`async_dsn` rewrites the scheme to the
``postgresql+asyncpg://`` driver SQLAlchemy's async engine requires.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import NewType

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import get_settings

#: A privileged, **RLS-bypassing** session for the server-only cost-guard counters (group 3.1). It
#: is a distinct type from a plain :class:`AsyncSession` so the cost-guard code path is visible in
#: signatures (it is what :func:`app.deps.get_usage_db` yields); it runs as the connecting
#: ``postgres`` role and must never be RLS-bound or used for per-user application data.
UsageSession = NewType("UsageSession", AsyncSession)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def async_dsn(url: str) -> str:
    """Return ``url`` rewritten to use SQLAlchemy's ``postgresql+asyncpg`` driver scheme.

    Only the scheme prefix is rewritten, so credentials, host, and any query string are
    preserved verbatim. A DSN that already names the asyncpg driver (or isn't a Postgres URL at
    all) is returned unchanged.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it from ``DATABASE_URL`` on first use."""
    global _engine
    if _engine is None:
        dsn = get_settings().database_url
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set; the database engine cannot be created.")
        _engine = create_async_engine(async_dsn(dsn), pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async sessionmaker bound to :func:`get_engine`."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an :class:`AsyncSession`, closing it when the request ends."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine and reset the singletons (FastAPI shutdown / test teardown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
