"""Tests for the ``/health`` (liveness) and ``/ready`` (readiness) probes — task 6.1.2.

``/health`` is a pure liveness probe: it returns ``200`` *always*, doing no DB/LLM work, so a
transient database blip never makes Cloud Run kill the instance. ``/ready`` is the readiness probe:
it runs a lightweight ``SELECT 1`` on a plain (RLS-free) engine connection and answers ``200``
when the DB is reachable and ``503`` (never ``500``) when it is not.

The DB-up path is proven two ways: offline with a stubbed engine (``_FakeEngine`` — so the success
branch + the whole ``_ping_db`` body run with no Postgres and no event-loop binding), and against
the real throwaway Postgres in an ``@integration`` test. The DB-down path is proven by making the
engine factory raise.
"""

from __future__ import annotations

import os
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient

import app.db.session as session_mod
from app.main import app
from app.settings import Settings

client = TestClient(app)


# ── Stubs ────────────────────────────────────────────────────────────────────────────────────────
class _FakeConn:
    """Minimal async stand-in for ``AsyncConnection`` so the readiness ``SELECT 1`` runs offline."""

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, statement: object) -> None:
        """No-op execute — the readiness check needs no real driver to exercise its happy path."""


class _FakeEngine:
    """Stub whose ``connect()`` yields a :class:`_FakeConn` (no real DB / event-loop binding)."""

    def connect(self) -> _FakeConn:
        return _FakeConn()


def _raise_no_database() -> NoReturn:
    """Stand-in for ``get_engine`` that fails like an unset/unreachable ``DATABASE_URL`` would."""
    raise RuntimeError("DATABASE_URL is not set; the database engine cannot be created.")


# ── /health (liveness) ───────────────────────────────────────────────────────────────────────────
def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_ok_even_when_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Liveness must NOT depend on the DB: ``/health`` stays ``200`` even if the engine can't build.

    ``get_engine`` is patched to raise, but ``/health`` does no DB work, so it is unaffected.
    """
    monkeypatch.setattr(session_mod, "get_engine", _raise_no_database)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── /ready (readiness) ───────────────────────────────────────────────────────────────────────────
def test_ready_returns_503_when_database_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A DB connectivity failure answers ``503 not_ready`` — never a ``500``."""
    monkeypatch.setattr(session_mod, "get_engine", _raise_no_database)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ready_returns_200_when_database_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful ``SELECT 1`` (stubbed engine) answers ``200 ready`` — runs offline."""
    monkeypatch.setattr(session_mod, "get_engine", lambda: _FakeEngine())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_db_ready_true_against_real_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """``check_db_ready`` connects to the real throwaway Postgres and returns ``True`` (CI path)."""
    # Mirror tests/conftest.py's DSN resolution so we point the app engine at the SAME reachable
    # Postgres the @integration guard probed (env, else the local Supabase CLI default), and build
    # a FRESH engine in this test's event loop via reset_engine_singletons-style teardown.
    dsn = os.getenv("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    monkeypatch.setattr(session_mod, "get_settings", lambda: Settings(database_url=dsn))
    session_mod._engine = None
    session_mod._sessionmaker = None
    try:
        assert await session_mod.check_db_ready() is True
    finally:
        await session_mod.dispose_engine()
