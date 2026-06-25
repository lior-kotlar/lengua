"""Fixtures for the HTTP API tests (Phase 1.5).

:func:`api_client` builds a fresh app and drives it in-process over ASGI (``httpx.AsyncClient`` +
``ASGITransport``) so requests share the test's own event loop and transaction:

- ``get_db`` is overridden to yield the test's :func:`tests.conftest.db_session` (a connection in
  an outer transaction rolled back at teardown), and the override does **not** close it — so the
  test can query the same session after a request to assert what was written.
- ``get_llm_provider`` is overridden to the deterministic :class:`FakeLLM` (no network/quota).
- The fixed-UUID dev user (``current_user``) is seeded first via :func:`scripts.seed_dev_user`
  so FK-bound inserts resolve against a real ``profiles`` row.

These tests are integration tests (they need the local Supabase Postgres + Auth); they auto-skip
when the DB is unreachable via the autouse guard in :mod:`tests.conftest`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_llm_provider
from app.main import create_app
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import DEV_USER_ID as _DEV_USER_ID
from scripts.seed_dev_user import seed_dev_user
from tests.conftest import _skip_if_db_unreachable

DEV_USER_UUID = uuid.UUID(_DEV_USER_ID)


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An ``AsyncClient`` bound to a fresh app whose DB + LLM dependencies are test-overridden."""
    _skip_if_db_unreachable()
    seed_dev_user()  # fixed-UUID dev profile so current_user's FK-bound inserts resolve

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # do not close — the test still queries this session afterwards

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
