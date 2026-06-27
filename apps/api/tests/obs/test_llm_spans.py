"""Task 5.2.1 verify: each LLM op emits an ``llm.call`` span with the full per-op attribute set.

Drives a real ``POST /generate`` / ``POST /discover`` / ``POST /explain`` (provider = deterministic
``FakeLLM``, zero real LLM calls) through the full router → guard → ``run_provider`` stack and
asserts the single ``llm.call`` span each op produced carries the span name, ``llm.model``, the
token attributes, the quota-gate-blocked attribute (``quota.cap_hit``), and the new per-op
``llm.input_size`` (words for generate / count for discover / 1 for explain) + ``llm.retry_count``.

``@pytest.mark.integration`` — needs the local Supabase stack; auto-skips when the DB is down.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.deps import DEV_USER_ID
from app.llm_observability import LLM_SPAN_NAME
from lengua_core.cards import PRODUCTION
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: Attributes every successful ``llm.call`` span must carry (3.8.1 + the 5.2.1 additions).
_REQUIRED_ATTRS = {
    "llm.provider",
    "llm.model",
    "llm.latency_ms",
    "llm.tokens_in",
    "llm.tokens_out",
    "llm.input_size",
    "llm.retry_count",
    "quota.kind",
    "quota.cap_hit",
}


def _only_llm_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    """The single captured ``llm.call`` span (fails if zero or more than one)."""
    spans = [s for s in exporter.get_finished_spans() if s.name == LLM_SPAN_NAME]
    assert len(spans) == 1, f"expected exactly one llm.call span, got {len(spans)}"
    return spans[0]


def _assert_common(attrs: dict[str, object], *, kind: str, input_size: int) -> None:
    assert attrs.keys() >= _REQUIRED_ATTRS, f"missing: {_REQUIRED_ATTRS - attrs.keys()}"
    assert attrs["llm.provider"] == "fake"
    assert attrs["llm.model"] == "fake"
    assert attrs["quota.kind"] == kind
    assert attrs["quota.cap_hit"] == "none"  # all three calls are admitted
    assert attrs["llm.input_size"] == input_size
    assert attrs["llm.retry_count"] == 0  # FakeLLM never retries
    assert isinstance(attrs["llm.tokens_in"], int) and attrs["llm.tokens_in"] >= 0
    assert isinstance(attrs["llm.tokens_out"], int) and attrs["llm.tokens_out"] > 0


async def test_each_op_emits_llm_call_span(
    multiuser_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    headers = auth_header(DEV_USER_ID)
    created = await multiuser_client.post(
        "/languages", json={"name": "Spanish", "code": "es"}, headers=headers
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]

    # Seed a saved deck so /explain has a production card whose sentence we can tap a word in.
    gen = await multiuser_client.post(
        "/generate", json={"language_id": language_id, "words": ["hola"]}, headers=headers
    )
    assert gen.status_code == 200, gen.text
    saved = await multiuser_client.post(
        "/cards/save", json={"language_id": language_id, "cards": gen.json()}, headers=headers
    )
    assert saved.status_code == 200, saved.text
    production = next(c for c in saved.json() if c["direction"] == PRODUCTION)

    # ── generate: input_size == number of words ──────────────────────────────────────────────────
    span_exporter.clear()
    r = await multiuser_client.post(
        "/generate", json={"language_id": language_id, "words": ["uno", "dos"]}, headers=headers
    )
    assert r.status_code == 200, r.text
    _assert_common(
        dict(_only_llm_span(span_exporter).attributes or {}), kind="generate", input_size=2
    )

    # ── discover: input_size == requested count ──────────────────────────────────────────────────
    span_exporter.clear()
    r = await multiuser_client.post(
        "/discover", json={"language_id": language_id, "count": 4}, headers=headers
    )
    assert r.status_code == 200, r.text
    _assert_common(
        dict(_only_llm_span(span_exporter).attributes or {}), kind="discover", input_size=4
    )

    # ── explain: input_size == 1; an uncached word in the sentence forces a provider call ─────────
    span_exporter.clear()
    r = await multiuser_client.post(
        "/explain",
        json={
            "language_id": language_id,
            "word": "sentence",  # appears in the FakeLLM sentence, not a saved used-word → miss
            "sentence": production["back"],
            "translation": production["front"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    _assert_common(
        dict(_only_llm_span(span_exporter).attributes or {}), kind="explain", input_size=1
    )
