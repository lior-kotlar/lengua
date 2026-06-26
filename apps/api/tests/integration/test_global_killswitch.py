"""End-to-end global kill-switch integration test (task 3.4.4).

Proves the budget is **GLOBAL, not per-user**: with ``GLOBAL_DAILY_BUDGET`` overridden to a small
value, user **A** drives real HTTP ``POST /generate`` calls (provider = deterministic ``FakeLLM``,
zero real LLM calls) until the project-wide budget is spent, and then user **B** — who has spent
nothing of their own per-user allowance — also gets the friendly ``daily_limit_reached`` response.
Once the budget is spent the provider is never called again, so blocked requests burn no budget and
no real quota.

This drives the *real* router → service → repository → cost-guard stack with a real JWT per request
(so one test can act as two users), only swapping the provider for the offline ``FakeLLM`` and the
DB/usage sessions for the rolled-back ``db_session``. ``@pytest.mark.integration`` — needs the local
Supabase stack; auto-skips when the DB is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.main import create_app
from app.quota import DAILY_LIMIT_MESSAGE, _utc_today
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import TEST_JWT_SECRET, auth_header
from tests.conftest import _skip_if_db_unreachable

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: The project-wide ceiling for this test. Kept BELOW the day-0 generate clamp (5) so the GLOBAL
#: budget — not user A's per-user cap — is the binding constraint that trips.
BUDGET = 3

#: User A is the seeded dev profile (created today → day-0); user B is a distinct, token-only
#: identity that owns no rows and has spent none of its own per-user allowance.
USER_A = DEV_USER_ID
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")

_FRIENDLY_BODY = {"code": "daily_limit_reached", "message": DAILY_LIMIT_MESSAGE}


def _killswitch_settings() -> Settings:
    """Real JWT verification (test secret) + a tiny global budget, generous per-user caps."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwt_secret=TEST_JWT_SECRET,
        supabase_jwks_url="",
        global_daily_budget=BUDGET,
        max_generate_per_day=50,
        default_generate_per_day=20,
        new_account_day0_generate_cap=5,
    )


@pytest_asyncio.fixture
async def killswitch_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An ASGI client verifying real JWTs, wired to the rolled-back DB + FakeLLM + a tiny budget."""
    _skip_if_db_unreachable()
    seed_dev_user()  # committed profile for user A so its inserts resolve

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # do not close — the test queries the same session afterwards

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    # A fresh, effectively-unlimited per-user rate limiter so the per-minute ceiling never trips
    # first and no process-wide window bleeds in from another test.
    limiter = InProcessRateLimiter(limit=1_000_000)

    def _override_rate_limiter() -> RateLimiter:
        return limiter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
    app.dependency_overrides[get_settings] = _killswitch_settings
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


async def test_global_killswitch_trips_across_users(
    killswitch_client: AsyncClient, db_session: AsyncSession
) -> None:
    usage = UsageRepository(db_session)
    today = _utc_today()

    # User A owns a language so /generate reaches the provider on each allowed call.
    created = await killswitch_client.post(
        "/languages", json={"name": "Spanish", "code": "es"}, headers=auth_header(USER_A)
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]
    gen_body = {"language_id": language_id, "words": ["hola"]}

    # User A spends the ENTIRE global budget: BUDGET successful generates (each bumps llm_budget by
    # 1 on success). A's day-0 generate cap is 5 > BUDGET, so the GLOBAL budget — not A's per-user
    # cap — is what binds.
    for n in range(BUDGET):
        ok = await killswitch_client.post("/generate", json=gen_body, headers=auth_header(USER_A))
        assert ok.status_code == 200, f"call {n} unexpectedly blocked: {ok.text}"
    assert await usage.get_budget_count(today) == BUDGET
    assert FakeLLM.call_count == BUDGET  # only the successful spends called the provider

    # User A is now refused with the friendly kill-switch body (budget spent, A still under its own
    # per-user cap).
    a_blocked = await killswitch_client.post(
        "/generate", json=gen_body, headers=auth_header(USER_A)
    )
    assert a_blocked.status_code == 429
    assert a_blocked.json() == _FRIENDLY_BODY

    # THE KEY ASSERTION: a DIFFERENT user B — who has spent NONE of their own per-user allowance —
    # is also refused with the same friendly body. The budget is GLOBAL, not per-user. (The budget
    # gate is a route dependency, so it rejects before the body — B needs no language of their own.)
    b_blocked = await killswitch_client.post(
        "/generate", json=gen_body, headers=auth_header(USER_B)
    )
    assert b_blocked.status_code == 429
    assert b_blocked.json() == _FRIENDLY_BODY

    # B truly spent nothing of their own (proves it was the global budget, not B's per-user cap),
    # the global counter never overshot the ceiling, and no extra provider calls happened — zero
    # real LLM usage beyond the BUDGET allowed spends.
    assert await usage.get_user_daily_count(USER_B, "generate", today) == 0
    assert await usage.get_budget_count(today) == BUDGET
    assert FakeLLM.call_count == BUDGET
