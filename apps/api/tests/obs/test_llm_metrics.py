"""Task 3.8.2 verify: the cost-guard metrics — call/cap-hit counters + the budget-remaining gauge.

``test_counters_and_gauge`` drives real ``POST /generate`` traffic (provider = ``FakeLLM``) until a
per-user daily cap trips, then collects an in-memory metric reader and asserts:

* ``llm_calls_total{kind, result}`` counts the successes and the blocked call;
* ``llm_cap_hits_total{gate=daily_cap}`` incremented when the cap tripped; and
* the ``llm_budget_remaining`` gauge reports ``GLOBAL_DAILY_BUDGET - llm_budget[today]``.

The remaining tests cover the no-op-without-endpoint meter-provider build (zero egress by default)
and the budget-remaining peek helper.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    PeriodicExportingMetricReader,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.llm_observability import (
    _build_meter_provider,
    _otlp_metrics_endpoint,
    peek_budget_remaining,
    set_budget_remaining,
)
from app.main import create_app
from app.quota import _utc_today
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import authenticate_as
from tests.conftest import _skip_if_db_unreachable

#: Tiny ceilings so the per-user daily ``generate`` cap (2) trips well before the global budget (5).
BUDGET = 5
GENERATE_CAP = 2


def _metrics_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        global_daily_budget=BUDGET,
        max_generate_per_day=50,
        default_generate_per_day=GENERATE_CAP,
        new_account_day0_generate_cap=GENERATE_CAP,
    )


@pytest_asyncio.fixture
async def metrics_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An ASGI client on the rolled-back DB + FakeLLM + tiny caps, authenticated as the dev user."""
    _skip_if_db_unreachable()
    seed_dev_user()  # committed dev profile (created today → day-0)

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    def _override_rate_limiter() -> RateLimiter:
        return InProcessRateLimiter(limit=1_000_000)  # generous: the daily cap is what binds here

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
    app.dependency_overrides[get_settings] = _metrics_settings
    authenticate_as(app, DEV_USER_ID, email_verified=True)
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def _counter_value(reader: InMemoryMetricReader, name: str, attrs: Mapping[str, str]) -> int:
    """The value of counter ``name`` for the data point matching exactly ``attrs`` (0 if none)."""
    data = reader.get_metrics_data()
    if data is None:
        return 0
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name != name:
                    continue
                for dp in metric.data.data_points:
                    if dict(dp.attributes) == dict(attrs):
                        return int(dp.value)
    return 0


def _gauge_values(reader: InMemoryMetricReader, name: str) -> list[float]:
    """All observed values for gauge ``name`` (empty when it has reported nothing yet)."""
    data = reader.get_metrics_data()
    values: list[float] = []
    if data is None:
        return values
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    values.extend(dp.value for dp in metric.data.data_points)
    return values


@pytest.mark.integration
@pytest.mark.asyncio
async def test_counters_and_gauge(
    metrics_client: AsyncClient,
    metric_reader: InMemoryMetricReader,
    db_session: AsyncSession,
) -> None:
    today = _utc_today()
    usage = UsageRepository(db_session)

    # Before any LLM traffic the gauge has observed nothing (the no-budget-yet branch).
    assert _gauge_values(metric_reader, "llm_budget_remaining") == []

    created = await metrics_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200, created.text
    gen = {"language_id": created.json()["id"], "words": ["hola"]}

    # Two successful generates exhaust the per-user daily cap (2); the third trips it.
    for _ in range(GENERATE_CAP):
        ok = await metrics_client.post("/generate", json=gen)
        assert ok.status_code == 200, ok.text
    blocked = await metrics_client.post("/generate", json=gen)
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "daily_cap_reached", "kind": "generate"}

    # Counters: two successes, one blocked call, one cap-hit attributed to the daily-cap gate.
    assert (
        _counter_value(metric_reader, "llm_calls_total", {"kind": "generate", "result": "success"})
        == GENERATE_CAP
    )
    assert (
        _counter_value(metric_reader, "llm_calls_total", {"kind": "generate", "result": "blocked"})
        == 1
    )
    assert _counter_value(metric_reader, "llm_cap_hits_total", {"gate": "daily_cap"}) == 1

    # Gauge: the latest reading is GLOBAL_DAILY_BUDGET - today's spent budget count.
    budget_count = await usage.get_budget_count(today)
    assert budget_count == GENERATE_CAP  # only the successful spends burned budget
    gauge = _gauge_values(metric_reader, "llm_budget_remaining")
    assert gauge[-1] == BUDGET - budget_count


def test_meter_provider_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert _otlp_metrics_endpoint() is None
    provider = _build_meter_provider()
    try:
        # No endpoint → no metric readers, so measurements are dropped (zero network egress).
        assert len(provider._metric_readers) == 0
    finally:
        provider.shutdown()


def test_meter_provider_attaches_otlp_reader_with_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    assert _otlp_metrics_endpoint() == "http://localhost:4317"
    provider = _build_meter_provider()
    try:
        readers = list(provider._metric_readers)
        assert len(readers) == 1
        assert isinstance(readers[0], PeriodicExportingMetricReader)
    finally:
        provider.shutdown()  # stops the periodic worker + closes the (never-connected) exporter


def test_peek_budget_remaining_default_then_known(metric_reader: InMemoryMetricReader) -> None:
    # The fixture resets the gauge's backing value, so peek first returns the supplied default…
    assert peek_budget_remaining(42) == 42
    # …then the last value once one has been observed.
    set_budget_remaining(7)
    assert peek_budget_remaining(42) == 7
    assert _gauge_values(metric_reader, "llm_budget_remaining") == [7]
