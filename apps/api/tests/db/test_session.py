"""Tests for the async SQLAlchemy session layer (task 1.3.1).

The pure DSN normalization and the engine/sessionmaker wiring are unit-tested offline (no DB
needed — the dummy engine is never actually connected to); one ``@pytest.mark.integration`` test
opens a real :class:`AsyncSession` against the throwaway Postgres and runs ``SELECT 1`` (the
literal task verify).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as session_mod
from app.db.session import async_dsn, get_db, get_engine
from app.settings import Settings


@pytest.fixture
def reset_engine_singletons() -> Iterator[None]:
    """Null out the module-level engine/sessionmaker around a test that builds its own."""
    session_mod._engine = None
    session_mod._sessionmaker = None
    yield
    session_mod._engine = None
    session_mod._sessionmaker = None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres",
        ),
        ("postgres://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
        ("postgresql+asyncpg://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
        ("sqlite+aiosqlite:///./x.db", "sqlite+aiosqlite:///./x.db"),
    ],
)
def test_async_dsn_rewrites_scheme(raw: str, expected: str) -> None:
    assert async_dsn(raw) == expected


def test_get_engine_requires_database_url(
    monkeypatch: pytest.MonkeyPatch, reset_engine_singletons: None
) -> None:
    monkeypatch.setattr(session_mod, "get_settings", lambda: Settings(database_url=""))
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_engine()


@pytest.mark.asyncio
async def test_get_db_yields_session_without_connecting(
    monkeypatch: pytest.MonkeyPatch, reset_engine_singletons: None
) -> None:
    # A syntactically valid DSN that is never connected to (the test executes no SQL), so this
    # exercises get_engine/get_sessionmaker/get_db/dispose_engine with no database required.
    monkeypatch.setattr(
        session_mod,
        "get_settings",
        lambda: Settings(database_url="postgresql://u:p@127.0.0.1:5432/lengua_unit"),
    )
    gen = get_db()
    session = await gen.__anext__()
    assert isinstance(session, AsyncSession)
    # The engine + sessionmaker are process-wide singletons (same object on repeat calls — this
    # also exercises the "already created" branch of each getter).
    assert session_mod.get_engine() is session_mod.get_engine()
    assert session_mod.get_sessionmaker() is session_mod.get_sessionmaker()
    await gen.aclose()
    await session_mod.dispose_engine()


@pytest.mark.asyncio
async def test_dispose_engine_is_noop_when_unset(reset_engine_singletons: None) -> None:
    session_mod._engine = None
    await session_mod.dispose_engine()  # must not raise when there is no engine yet


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_runs_select_one(db_session: AsyncSession) -> None:
    """Open a real async session against the throwaway Postgres and run ``SELECT 1``."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
