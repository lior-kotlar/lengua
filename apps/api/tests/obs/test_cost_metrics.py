"""Task 5.2.4 verify: the cost/LLM counters + gauges, including the new ``llm_tokens_total``.

Drives real ``POST /generate`` traffic (provider = ``FakeLLM``) until a per-user daily cap trips,
then collects an in-memory metric reader and asserts:

* ``llm_calls_total{kind=generate, result=success}`` counted the admitted calls;
* ``llm_budget_remaining`` (gauge) decreased below the ceiling;
* ``llm_cap_hits_total`` — the plan's ``quota_blocks_total{reason}`` (``gate`` == reason) —
  incremented when the cap tripped; and
* ``llm_tokens_total{kind=generate, direction}`` incremented (the new counter).

``@pytest.mark.integration`` — needs the local Supabase stack; auto-skips when the DB is down.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.main import create_app
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.settings import Settings, get_settings
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import authenticate_as
from tests.conftest import _skip_if_db_unreachable
from tests.obs.conftest import counter_value, gauge_values, sum_counter

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BUDGET = 5
GENERATE_CAP = 2  # the per-user daily generate cap trips on the 3rd call


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        global_daily_budget=BUDGET,
        max_generate_per_day=50,
        default_generate_per_day=GENERATE_CAP,
        new_account_day0_generate_cap=GENERATE_CAP,
    )


@pytest_asyncio.fixture
async def cost_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI client on the rolled-back DB + FakeLLM + tiny caps, authenticated as the dev user."""
    _skip_if_db_unreachable()
    seed_dev_user()
    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    def _override_rate_limiter() -> RateLimiter:
        return InProcessRateLimiter(limit=1_000_000)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
    app.dependency_overrides[get_settings] = _settings
    authenticate_as(app, DEV_USER_ID, email_verified=True)
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


async def test_cost_counters_gauge_and_tokens(
    cost_client: AsyncClient, metric_reader: InMemoryMetricReader
) -> None:
    created = await cost_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200, created.text
    gen = {"language_id": created.json()["id"], "words": ["hola"]}

    # Before any LLM traffic the budget gauge has observed nothing.
    assert gauge_values(metric_reader, "llm_budget_remaining") == []

    # Two successful generates exhaust the per-user daily cap (2); the third trips it.
    for _ in range(GENERATE_CAP):
        ok = await cost_client.post("/generate", json=gen)
        assert ok.status_code == 200, ok.text
    blocked = await cost_client.post("/generate", json=gen)
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "daily_cap_reached", "kind": "generate"}

    # llm_calls_total{kind=generate}: the admitted successes.
    assert (
        counter_value(metric_reader, "llm_calls_total", {"kind": "generate", "result": "success"})
        == GENERATE_CAP
    )
    # llm_cap_hits_total IS the plan's quota_blocks_total (gate == reason): one daily-cap block.
    assert counter_value(metric_reader, "llm_cap_hits_total", {"gate": "daily_cap"}) == 1

    # llm_budget_remaining decreased below the ceiling (only the successful spends burned budget).
    gauge = gauge_values(metric_reader, "llm_budget_remaining")
    assert gauge, "expected the budget gauge to have reported a value"
    assert gauge[-1] == BUDGET - GENERATE_CAP < BUDGET

    # llm_tokens_total{kind=generate, direction} incremented on the successful calls (task 5.2.4);
    # the blocked call recorded no tokens.
    tokens_in = counter_value(
        metric_reader, "llm_tokens_total", {"kind": "generate", "direction": "in"}
    )
    tokens_out = counter_value(
        metric_reader, "llm_tokens_total", {"kind": "generate", "direction": "out"}
    )
    assert tokens_in > 0
    assert tokens_out > 0
    assert sum_counter(metric_reader, "llm_tokens_total") == tokens_in + tokens_out
