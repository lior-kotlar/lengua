"""Task 3.8.1 verify: every LLM call emits an ``llm.call`` span carrying the full attribute set.

``test_span_attributes`` drives one real ``POST /generate`` (provider = deterministic ``FakeLLM``,
zero real LLM calls) through the full router → guard → ``run_provider`` stack and asserts the single
``llm.call`` span the in-memory exporter captured carries **all** the listed attributes:
``llm.provider`` / ``llm.model`` / ``llm.latency_ms`` / ``llm.tokens_in`` / ``llm.tokens_out`` +
``quota.kind`` / ``quota.cap_hit`` / ``budget.remaining``. ``@pytest.mark.integration`` — it needs
the local Supabase stack; auto-skips when the DB is unreachable.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.deps import DEV_USER_ID
from app.llm_observability import LLM_SPAN_NAME
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: Every attribute the per-call span must carry for one admitted (successful) fake call.
_REQUIRED_ATTRS = {
    "llm.provider",
    "llm.model",
    "llm.latency_ms",
    "llm.tokens_in",
    "llm.tokens_out",
    "quota.kind",
    "quota.cap_hit",
    "budget.remaining",
}


async def test_span_attributes(
    multiuser_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    # User A owns a language so /generate reaches the provider and emits an llm.call span.
    created = await multiuser_client.post(
        "/languages", json={"name": "Spanish", "code": "es"}, headers=auth_header(DEV_USER_ID)
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]

    ok = await multiuser_client.post(
        "/generate",
        json={"language_id": language_id, "words": ["hola", "mundo"]},
        headers=auth_header(DEV_USER_ID),
    )
    assert ok.status_code == 200, ok.text

    llm_spans = [s for s in span_exporter.get_finished_spans() if s.name == LLM_SPAN_NAME]
    assert len(llm_spans) == 1, f"expected exactly one llm.call span, got {len(llm_spans)}"
    attrs = dict(llm_spans[0].attributes or {})

    assert attrs.keys() >= _REQUIRED_ATTRS, f"missing: {_REQUIRED_ATTRS - attrs.keys()}"
    # The fake provider's identity + an admitted call's cost-guard context.
    assert attrs["llm.provider"] == "fake"
    assert attrs["llm.model"] == "fake"
    assert attrs["quota.kind"] == "generate"
    assert attrs["quota.cap_hit"] == "none"
    # Types/shape: latency is a non-negative float, tokens are non-negative ints, and a single
    # successful spend leaves GLOBAL_DAILY_BUDGET - 1 remaining (the default budget is 1000).
    assert isinstance(attrs["llm.latency_ms"], float) and attrs["llm.latency_ms"] >= 0
    assert isinstance(attrs["llm.tokens_in"], int) and attrs["llm.tokens_in"] >= 0
    assert isinstance(attrs["llm.tokens_out"], int) and attrs["llm.tokens_out"] > 0
    assert attrs["budget.remaining"] == 1000 - 1
