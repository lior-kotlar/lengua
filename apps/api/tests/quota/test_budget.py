"""Global daily budget kill-switch tests (tasks 3.4.2 / 3.4.3).

The kill-switch is the "I will never get a bill" backstop — the LAST gate, evaluated after the
per-user daily cap. These prove the two correctness properties that matter most:

* :func:`test_kill_switch_trips` (3.4.2) — once the GLOBAL ``llm_budget`` counter reaches
  :data:`~app.settings.Settings.global_daily_budget` the gate refuses *every* caller with the
  friendly body ``{"code": "daily_limit_reached", "message": ...}`` (asserted over real HTTP); below
  the ceiling the gate allows. Because the budget gate is a route *dependency* it rejects before the
  route body, so the provider is never called.
* :func:`test_failed_call_no_increment` (3.4.3) — a failed provider call leaves BOTH counters
  (``llm_usage`` + ``llm_budget``) unchanged, while a successful call bumps BOTH by exactly 1 (the
  single atomic increment). This is the check-then-increment-on-success contract: only a successful
  spend burns budget.

All touch the DB (the ``SECURITY DEFINER`` counter functions + ``user_settings``), so they are
``@pytest.mark.integration`` and run against the local Supabase stack on the rolled-back
``db_session`` (superuser, which retains EXECUTE on the definer functions); every write — including
the global ``llm_budget`` bump — is undone at teardown, so nothing leaks between tests.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID, get_llm_provider
from app.quota import (
    DAILY_LIMIT_MESSAGE,
    GlobalBudgetReached,
    QuotaGuard,
    _utc_today,
)
from app.ratelimit import InProcessRateLimiter, get_rate_limiter
from app.repositories.languages import LanguagesRepository
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings
from lengua_core.llm.fake import FakeLLM
from lengua_core.models import GeneratedCard
from tests.auth_helpers import authenticate_as
from tests.quota.conftest import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _budget_settings(global_daily_budget: int) -> Settings:
    """Settings with env-independent quota ceilings and an explicit global budget under test."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        max_generate_per_day=50,
        max_discover_per_day=30,
        max_explain_per_day=100,
        default_generate_per_day=20,
        default_discover_per_day=10,
        default_explain_per_day=50,
        new_account_day0_generate_cap=5,
        global_daily_budget=global_daily_budget,
    )


def _generate_guard(db_session: AsyncSession, settings: Settings) -> QuotaGuard:
    """A verified-user ``generate`` guard with an effectively-unlimited limiter.

    The privileged usage session stands in as the superuser ``db_session`` (which keeps EXECUTE on
    the definer functions), so the budget read/increment hit the same rolled-back transaction the
    test asserts on.
    """
    return QuotaGuard(
        kind="generate",
        user_id=DEV_USER_ID,
        email_verified=True,
        db=db_session,
        usage_db=db_session,  # type: ignore[arg-type]  # superuser stands in for UsageSession
        settings=settings,
        rate_limiter=InProcessRateLimiter(limit=1000),
    )


async def test_kill_switch_trips(quota_app: FastAPI, db_session: AsyncSession) -> None:
    budget_ceiling = 3
    authenticate_as(quota_app, DEV_USER_ID, email_verified=True)
    quota_app.dependency_overrides[get_settings] = lambda: _budget_settings(budget_ceiling)
    # Pin a generous, isolated limiter so the process-wide singleton can't reject our one request.
    quota_app.dependency_overrides[get_rate_limiter] = lambda: InProcessRateLimiter(limit=1000)

    usage = UsageRepository(db_session)
    today = _utc_today()

    # Pump the GLOBAL budget to one BELOW the ceiling via ``discover`` increments — this bumps the
    # global ``llm_budget`` (and the user's discover count) but NOT the generate count, so the
    # generate daily-cap gate stays clear and only the budget gate is exercised below.
    for _ in range(budget_ceiling - 1):
        await usage.increment_usage(DEV_USER_ID, "discover", today)
    assert await usage.get_budget_count(today) == budget_ceiling - 1

    # Below the ceiling → the gate ALLOWS (no exception).
    guard = _generate_guard(db_session, _budget_settings(budget_ceiling))
    await guard.check()

    # Push the budget to the ceiling.
    await usage.increment_usage(DEV_USER_ID, "discover", today)
    assert await usage.get_budget_count(today) == budget_ceiling

    # At the ceiling, a real HTTP POST /generate is refused with the friendly kill-switch body. The
    # budget gate is a route DEPENDENCY, so it rejects before the route body — no language is needed
    # and the provider is never touched.
    FakeLLM.reset_call_count()
    async with client_for(quota_app) as client:
        resp = await client.post("/generate", json={"language_id": 1, "words": ["hola"]})
    assert resp.status_code == 429
    assert resp.json() == {"code": "daily_limit_reached", "message": DAILY_LIMIT_MESSAGE}
    assert FakeLLM.call_count == 0

    # And the gate itself raises the typed kill-switch error once the ceiling is reached.
    with pytest.raises(GlobalBudgetReached):
        await guard.check()


class _BoomLLM:
    """A provider whose ``generate_cards`` fails — stands in for a real provider error (5xx).

    Implements the :class:`~lengua_core.llm.base.LLMProvider` Protocol structurally (rather than
    subclassing ``FakeLLM``) so the type checker sees a concrete provider; only ``generate_cards``
    is exercised here.
    """

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        raise RuntimeError("provider boom")

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def explain_word(self, word: str, sentence: str, translation: str, language: str) -> str:
        raise NotImplementedError


async def test_failed_call_no_increment(quota_app: FastAPI, db_session: AsyncSession) -> None:
    authenticate_as(quota_app, DEV_USER_ID, email_verified=True)
    # Leave the global budget at its (generous) default so the budget gate never trips here — this
    # test is about the increment, not the kill-switch. A fresh generous limiter keeps it isolated.
    quota_app.dependency_overrides[get_settings] = lambda: _budget_settings(1000)
    quota_app.dependency_overrides[get_rate_limiter] = lambda: InProcessRateLimiter(limit=1000)

    usage = UsageRepository(db_session)
    today = _utc_today()
    # A language the dev user owns, so GenerateService reaches the provider call.
    language = await LanguagesRepository(db_session).create(DEV_USER_ID, name="Spanish", code="es")
    gen_body = {"language_id": language.id, "words": ["hola"]}

    assert await usage.get_budget_count(today) == 0
    assert await usage.get_user_daily_count(DEV_USER_ID, "generate", today) == 0

    # ── Failure: the provider raises AFTER the gate passes → record_success is never reached, so
    # NEITHER counter moves. (raise_app_exceptions=False → we get the 500 response, not a re-raise.)
    quota_app.dependency_overrides[get_llm_provider] = lambda: _BoomLLM()
    transport = ASGITransport(app=quota_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        failed = await client.post("/generate", json=gen_body)
    assert failed.status_code == 500
    assert await usage.get_budget_count(today) == 0
    assert await usage.get_user_daily_count(DEV_USER_ID, "generate", today) == 0

    # ── Success: the provider returns → record_success bumps BOTH counters by exactly 1.
    quota_app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    async with client_for(quota_app) as client:
        ok = await client.post("/generate", json=gen_body)
    assert ok.status_code == 200
    assert await usage.get_budget_count(today) == 1
    assert await usage.get_user_daily_count(DEV_USER_ID, "generate", today) == 1
