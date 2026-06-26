"""Integration tests for :class:`app.repositories.usage.UsageRepository` (tasks 3.1.3 / 3.1.4).

These run against the live local Supabase stack (the ``SECURITY DEFINER`` increment/read functions
live there, built from the canonical SQL migration). Unlike most repo tests they do **not** use the
rolled-back ``db_session`` fixture: the atomicity test needs rows *committed* and visible across
many concurrent connections, so it drives its own engine/sessionmaker and cleans up afterwards.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid

import psycopg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import async_dsn
from app.repositories.usage import UsageRepository
from tests.conftest import _skip_if_db_unreachable, database_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _create_user() -> uuid.UUID:
    """Insert a fresh ``auth.users`` row (the trigger makes its ``profiles`` row); return its id."""
    uid = uuid.uuid4()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
            (uid, f"usage-{uid.hex[:12]}@lengua.test"),
        )
    return uid


def _delete_user(uid: uuid.UUID) -> None:
    """Delete the ``auth.users`` row (cascades to ``profiles`` → ``llm_usage``)."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("DELETE FROM auth.users WHERE id = %s", (uid,))


def _delete_budget(day: datetime.date) -> None:
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute("DELETE FROM llm_budget WHERE day = %s", (day,))


async def test_increment_is_atomic() -> None:
    """50 concurrent ``increment_usage`` calls leave ``count == 50`` in *both* counters.

    Each call runs on its own session/connection and commits, so they genuinely race; the function's
    row-locked ``ON CONFLICT DO UPDATE`` bumps serialize, so there are no lost updates in either
    ``llm_usage`` (the per-user counter) or ``llm_budget`` (the global counter).
    """
    _skip_if_db_unreachable()
    uid = _create_user()
    kind = "generate"
    day = datetime.date(2099, 3, 3)
    n = 50
    engine = create_async_engine(async_dsn(database_url()), pool_size=10, max_overflow=20)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _one_increment() -> int:
        async with sessionmaker() as session:
            count = await UsageRepository(session).increment_usage(uid, kind, day)
            await session.commit()
            return count

    try:
        results = await asyncio.gather(*[_one_increment() for _ in range(n)])
        # Every call saw a distinct budget value 1..50 (monotonic, no two callers got the same n).
        assert sorted(results) == list(range(1, n + 1)), (
            f"lost/duplicate updates: {sorted(results)}"
        )

        async with sessionmaker() as session:
            repo = UsageRepository(session)
            assert await repo.get_user_daily_count(uid, kind, day) == n
            assert await repo.get_budget_count(day) == n
    finally:
        await engine.dispose()
        _delete_user(uid)
        _delete_budget(day)


async def test_reads_default_zero() -> None:
    """``get_user_daily_count`` and ``get_budget_count`` return 0 for a fresh user/day (no rows)."""
    _skip_if_db_unreachable()
    fresh_user = uuid.uuid4()
    fresh_day = datetime.date(2099, 4, 4)
    engine = create_async_engine(async_dsn(database_url()))
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            repo = UsageRepository(session)
            assert await repo.get_user_daily_count(fresh_user, "generate", fresh_day) == 0
            assert await repo.get_budget_count(fresh_day) == 0
    finally:
        await engine.dispose()
