"""Shared fixtures for the Phase 3.3/3.7 cost-guard gate tests (email + rate-limit + day-0 clamp).

:func:`quota_app` builds the real app with the same DB / usage-session / LLM overrides as
``tests/api``'s ``api_client``, but **leaves auth and the rate limiter unpinned** so each test
installs exactly the identity (verified / unverified) and limiter (small limit + a fake clock) the
gate under test needs. Tests build an ``AsyncClient`` from the returned app via :func:`client_for`.

:class:`FakeClock` is the deterministic, manually-advanced clock the rate-limiter tests inject so a
window can be crossed without sleeping.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession
from app.deps import get_db, get_llm_provider, get_usage_db
from app.discover_cache import DiscoverCache, InProcessDiscoverCache, get_discover_cache
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.main import create_app
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.conftest import _skip_if_db_unreachable


class FakeClock:
    """A deterministic, manually-advanced monotonic-style clock for the rate-limiter tests."""

    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds`` (the test's stand-in for time passing)."""
        self._now += seconds


@pytest_asyncio.fixture
async def quota_app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """A fresh app wired to the test's rolled-back ``db_session`` + ``FakeLLM``, auth/rate unpinned.

    The DB, privileged usage session, and LLM provider are overridden exactly as in ``api_client``
    (so on-success increments stay inside the test transaction and no network/quota is touched), but
    the JWT identity and the rate limiter are deliberately left to each test to install.
    """
    _skip_if_db_unreachable()
    seed_dev_user()  # committed dev profile (created_at = today after the module truncate → day-0)

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # do not close — the test still queries this session afterwards

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    # Fresh, generous concurrency limiter (Phase 3.5) so the process-wide singleton's semaphore
    # never spans test event loops; the gate tests here never contend it.
    test_llm_limiter = LLMConcurrencyLimiter(max_concurrency=4)

    def _override_llm_limiter() -> LLMConcurrencyLimiter:
        return test_llm_limiter

    # Fresh discover reuse cache (Phase 3.6.3) with a frozen clock so the process-wide singleton
    # never bleeds across tests/event loops (the gate tests here drive ``/generate``, not discover).
    test_discover_cache = InProcessDiscoverCache(ttl_seconds=300.0, clock=lambda: 0.0)

    def _override_discover_cache() -> DiscoverCache:
        return test_discover_cache

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_llm_limiter] = _override_llm_limiter
    app.dependency_overrides[get_discover_cache] = _override_discover_cache
    FakeLLM.reset_call_count()

    yield app
    app.dependency_overrides.clear()


@contextlib.asynccontextmanager
async def client_for(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An ``AsyncClient`` driving ``app`` in-process over ASGI (matches the test's event loop)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
