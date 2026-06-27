"""Async SQLAlchemy engine, sessionmaker, and the ``get_db`` dependency (task 1.3.1).

A single async engine (asyncpg driver) and ``async_sessionmaker`` are created lazily from
``DATABASE_URL`` (read via :func:`app.settings.get_settings`) and reused process-wide;
:func:`get_db` is the FastAPI dependency that yields a short-lived :class:`AsyncSession`.

``DATABASE_URL`` is stored in the libpq/psycopg form (``postgresql://…``) — what Supabase, the
test ``conftest``, and ``.env`` all emit — so :func:`async_dsn` rewrites the scheme to the
``postgresql+asyncpg://`` driver SQLAlchemy's async engine requires.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import NewType

# Import the module (not just the symbol) so :func:`get_engine` can resolve ``create_async_engine``
# at *call* time — see the note in :func:`get_engine` for why the late binding matters for tracing.
import sqlalchemy.ext.asyncio as sa_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.settings import get_settings

#: How long the readiness probe waits for the database to answer before declaring "not ready".
#: Deliberately short — a readiness check must fail fast so Cloud Run can pull a wedged instance
#: from rotation rather than hang the probe (the startup/liveness probes hit the DB-free /health).
READY_CHECK_TIMEOUT_SECONDS = 5.0

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
    """Return the process-wide async engine, creating it from ``DATABASE_URL`` on first use.

    The engine is built via ``sqlalchemy.ext.asyncio.create_async_engine`` resolved on the module
    **at call time** (not a module-level ``from … import create_async_engine``). That late binding
    is load-bearing for observability (task 5.1.3): the OpenTelemetry SQLAlchemy
    auto-instrumentation wraps ``create_async_engine`` when
    :func:`app.observability.configure_observability` runs, and
    only engines built through that *wrapped* factory get the per-statement ``EngineTracer`` that
    emits ``SELECT``/``INSERT`` query spans. A module-level import would capture the *unwrapped*
    function (bound before instrumentation), leaving the app engine with only the class-level
    ``connect`` span and **no** statement spans — so each request's trace would miss its DB
    children. This is engine creation only — connections (and thus any network) are still lazy.
    """
    global _engine
    if _engine is None:
        dsn = get_settings().database_url
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set; the database engine cannot be created.")
        _engine = sa_asyncio.create_async_engine(async_dsn(dsn), pool_pre_ping=True)
    return _engine


async def _ping_db() -> None:
    """Run a trivial ``SELECT 1`` on a plain (RLS-free) engine connection.

    Uses :func:`get_engine` directly — the app engine, **not** the per-request RLS session — so it
    needs no JWT and never switches to the ``authenticated`` role. The connection is returned to the
    pool on exit; the process-wide engine is never disposed here.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def check_db_ready(timeout_seconds: float = READY_CHECK_TIMEOUT_SECONDS) -> bool:
    """Return ``True`` iff the database answers a ``SELECT 1`` within ``timeout_seconds``.

    The connectivity backend for the unauthenticated ``GET /ready`` readiness probe. The check is
    bounded by ``timeout_seconds`` (via :func:`asyncio.wait_for`) and catches **every** error — an
    unset ``DATABASE_URL``, a refused or slow connection, a timeout — returning ``False`` so the
    probe can answer ``503`` instead of surfacing a ``500``. It never raises.
    """
    try:
        await asyncio.wait_for(_ping_db(), timeout=timeout_seconds)
    except Exception:
        return False
    return True


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
