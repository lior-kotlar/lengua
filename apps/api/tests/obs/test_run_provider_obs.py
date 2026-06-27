"""Offline unit coverage for the ``run_provider`` boundary instrumentation (tasks 5.2.1 / 5.2.4).

Drives :func:`app.llm_runner.run_provider` directly against the deterministic ``FakeLLM`` (no DB, no
network) and asserts the per-call ``llm.call`` span carries the full attribute set — including the
new ``llm.input_size`` / ``llm.retry_count`` (5.2.1) — and that a successful call bumps
``llm_tokens_total{kind, direction}`` (5.2.4). Also exercises the no-span / no-kind pass-through so
every branch of the boundary is covered without the integration stack.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.llm_observability import (
    LLM_SPAN_NAME,
    QUOTA_CHECK_SPAN_NAME,
    record_tokens,
    start_llm_span,
    start_quota_check_span,
)
from app.llm_runner import LLMConcurrencyLimiter, run_provider
from lengua_core.llm.fake import FakeLLM
from tests.obs.conftest import counter_value, sum_counter

pytestmark = pytest.mark.asyncio


def _limiter() -> LLMConcurrencyLimiter:
    return LLMConcurrencyLimiter(max_concurrency=2)


async def test_run_provider_stamps_attrs_and_counts_tokens(
    span_exporter: InMemorySpanExporter, metric_reader: InMemoryMetricReader
) -> None:
    provider = FakeLLM()
    span = start_llm_span("generate")
    words = ["hola", "mundo"]

    cards = await run_provider(
        _limiter(),
        provider,
        span,
        lambda: provider.generate_cards(words, "Spanish", level_band="A1"),
        input_size=len(words),
        kind="generate",
    )
    span.end()
    assert len(cards) == len(words)  # the call actually ran

    finished = [s for s in span_exporter.get_finished_spans() if s.name == LLM_SPAN_NAME]
    assert len(finished) == 1
    attrs = dict(finished[0].attributes or {})
    assert attrs["llm.provider"] == "fake"
    assert attrs["llm.model"] == "fake"
    assert attrs["llm.input_size"] == 2
    assert attrs["llm.retry_count"] == 0  # FakeLLM never goes through call_with_retry
    tokens_in = attrs["llm.tokens_in"]
    tokens_out = attrs["llm.tokens_out"]
    assert isinstance(tokens_in, int) and tokens_in > 0
    assert isinstance(tokens_out, int) and tokens_out > 0

    # llm_tokens_total{kind, direction} matches the per-call token attributes (task 5.2.4).
    assert (
        counter_value(metric_reader, "llm_tokens_total", {"kind": "generate", "direction": "in"})
        == tokens_in
    )
    assert (
        counter_value(metric_reader, "llm_tokens_total", {"kind": "generate", "direction": "out"})
        == tokens_out
    )


async def test_run_provider_without_span_or_kind_is_passthrough(
    metric_reader: InMemoryMetricReader,
) -> None:
    # No span + no kind: a plain pass-through (a provider call outside a gated request). Nothing is
    # stamped and no token metric is recorded — covers the span-None / kind-None branches.
    provider = FakeLLM()
    result = await run_provider(
        _limiter(),
        provider,
        None,
        lambda: provider.explain_word("hola", "hola mundo", "hi world", "Spanish"),
    )
    assert isinstance(result, str) and result
    assert (
        counter_value(metric_reader, "llm_tokens_total", {"kind": "explain", "direction": "in"})
        == 0
    )


async def test_start_quota_check_span_names_and_tags_kind(
    span_exporter: InMemorySpanExporter,
) -> None:
    span = start_quota_check_span("discover")
    span.end()
    spans = [s for s in span_exporter.get_finished_spans() if s.name == QUOTA_CHECK_SPAN_NAME]
    assert len(spans) == 1
    assert dict(spans[0].attributes or {})["quota.kind"] == "discover"


async def test_record_tokens_zero_is_noop(metric_reader: InMemoryMetricReader) -> None:
    # A provider that reported no usage adds nothing (counters only go up): both branches no-op.
    record_tokens("explain", 0, 0)
    assert sum_counter(metric_reader, "llm_tokens_total") == 0


async def test_run_provider_span_without_input_size_or_kind(
    span_exporter: InMemorySpanExporter, metric_reader: InMemoryMetricReader
) -> None:
    # Span present but input_size/kind omitted: stamps provider/model/latency/tokens/retry but no
    # input_size, and records no token counter (covers the input_size-None + kind-None branches with
    # a live span).
    provider = FakeLLM()
    span = start_llm_span("discover")
    await run_provider(
        _limiter(),
        provider,
        span,
        lambda: provider.suggest_new_words("Spanish", "A1", [], count=3),
    )
    span.end()
    finished = [s for s in span_exporter.get_finished_spans() if s.name == LLM_SPAN_NAME]
    assert len(finished) == 1
    attrs = dict(finished[0].attributes or {})
    assert "llm.input_size" not in attrs
    assert attrs["llm.retry_count"] == 0
    assert (
        counter_value(metric_reader, "llm_tokens_total", {"kind": "discover", "direction": "in"})
        == 0
    )
