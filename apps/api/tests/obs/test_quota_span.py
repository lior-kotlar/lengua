"""Task 5.2.3 verify: every gated call emits a ``quota.check`` span with cap + budget state.

Drives an **admitted** ``POST /generate`` and a **blocked** one (a per-user daily cap of 1 trips on
the second call) and asserts each produced exactly one ``quota.check`` span carrying
``user.cap_remaining`` and ``budget.remaining`` — proving the gate span is emitted on both the admit
and the block path. ``@pytest.mark.integration`` — needs the Supabase stack; auto-skips offline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.llm_observability import (
    ATTR_BUDGET_REMAINING,
    ATTR_USER_CAP_REMAINING,
    QUOTA_CHECK_SPAN_NAME,
)
from app.main import create_app
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.settings import Settings, get_settings
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import authenticate_as
from tests.conftest import _skip_if_db_unreachable

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BUDGET = 1000
GENERATE_CAP = 1  # so the 2nd generate trips the per-user daily cap (the block path)


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        global_daily_budget=BUDGET,
        max_generate_per_day=50,
        default_generate_per_day=GENERATE_CAP,
        new_account_day0_generate_cap=GENERATE_CAP,
    )


@pytest_asyncio.fixture
async def quota_span_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI client on the rolled-back DB + FakeLLM with a generate cap of 1 (dev user, verified)."""
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
        return InProcessRateLimiter(limit=1_000_000)  # the daily cap is what binds here

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


def _only_quota_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    spans = [s for s in exporter.get_finished_spans() if s.name == QUOTA_CHECK_SPAN_NAME]
    assert len(spans) == 1, f"expected exactly one quota.check span, got {len(spans)}"
    return spans[0]


async def test_quota_check_span_on_admit_and_block(
    quota_span_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    created = await quota_span_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200, created.text
    body = {"language_id": created.json()["id"], "words": ["hola"]}

    # ── Admit: count 0 < cap 1 → succeeds; the gate span carries cap_remaining 1 and the budget. ──
    span_exporter.clear()
    admitted = await quota_span_client.post("/generate", json=body)
    assert admitted.status_code == 200, admitted.text
    attrs = dict(_only_quota_span(span_exporter).attributes or {})
    assert attrs["quota.kind"] == "generate"
    assert attrs[ATTR_USER_CAP_REMAINING] == 1  # cap(1) - count(0)
    assert attrs[ATTR_BUDGET_REMAINING] == BUDGET  # global gate read, nothing spent yet

    # ── Block: count 1 == cap 1 → 429 daily_cap_reached; the gate span still carries both attrs. ──
    span_exporter.clear()
    blocked = await quota_span_client.post("/generate", json=body)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json() == {"code": "daily_cap_reached", "kind": "generate"}
    attrs = dict(_only_quota_span(span_exporter).attributes or {})
    assert attrs[ATTR_USER_CAP_REMAINING] == 0  # cap(1) - count(1)
    # The daily-cap gate fires before the global-budget read, so budget.remaining is the last-known
    # value (the admit spent one) — present and an int on the block path.
    assert isinstance(attrs[ATTR_BUDGET_REMAINING], int)
    assert attrs[ATTR_BUDGET_REMAINING] == BUDGET - 1
