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

from app.db.session import UsageSession
from app.deps import get_db, get_llm_provider, get_usage_db
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.main import create_app
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import DEV_USER_ID as _DEV_USER_ID
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import authenticate_as
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

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        # The cost-guard's privileged usage session (Phase 3.2) shares the test's rolled-back
        # ``db_session`` instead of opening its own real connection. That keeps the on-success
        # increments inside the test transaction (no committed pollution, no cross-event-loop pool
        # reuse) AND lets them see rows the test created uncommitted (e.g. a token-only user's
        # profile). Safe because ``db_session`` runs as superuser, which keeps EXECUTE on the
        # ``SECURITY DEFINER`` increment function; production keeps the two sessions separate.
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    # The per-user rate limiter (Phase 3.3) is process-wide global state. Hand each test its own
    # fresh, effectively-unlimited limiter so the global window can't bleed across tests and the
    # generic API tests (which fire many gated calls) never trip the real per-minute ceiling — the
    # dedicated rate-limit tests in ``tests/quota`` install their own small-limit limiter instead.
    test_rate_limiter = InProcessRateLimiter(limit=1_000_000)

    def _override_rate_limiter() -> RateLimiter:
        return test_rate_limiter

    # The global concurrency cap (Phase 3.5) is process-wide asyncio state. Hand each test its own
    # fresh, generous limiter so the shared singleton's semaphore never spans test event loops.
    test_llm_limiter = LLMConcurrencyLimiter(max_concurrency=4)

    def _override_llm_limiter() -> LLMConcurrencyLimiter:
        return test_llm_limiter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
    app.dependency_overrides[get_llm_limiter] = _override_llm_limiter
    # Authenticate every request as the seeded dev user (routes now require a verified JWT; the
    # override stands in for one so the Phase 1 HTTP tests keep exercising the routers).
    authenticate_as(app, DEV_USER_UUID)
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
