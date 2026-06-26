"""Fixtures for the observability tests (Phase 1.7 + 3.8).

:func:`span_exporter` attaches an in-memory span exporter to the **global** SDK tracer provider
that :func:`app.main.create_app` installs — so the tests assert against the real wiring rather
than a bespoke provider — and removes it again at teardown so spans don't leak between tests.

:func:`metric_reader` swaps the cost-guard's module-owned :class:`MeterProvider` (``app
.llm_observability``) for one whose only reader is an in-memory reader, so the LLM metrics
(task 3.8.2) can be collected and asserted, restoring the previous provider at teardown.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Importing app.main runs the module-level ``app = create_app()``, which calls
# configure_observability() and installs the global SDK TracerProvider these fixtures rely on.
import app.main  # noqa: F401
from app import llm_observability


@pytest.fixture
def metric_reader() -> Iterator[InMemoryMetricReader]:
    """Yield an :class:`InMemoryMetricReader` wired into the cost-guard metric instruments.

    Installs a fresh, in-memory meter provider as the module's provider (rebuilding the instruments
    against it and clearing the budget-gauge value), so a test can drive LLM traffic and then
    ``reader.get_metrics_data()`` to assert the counters + gauge. Teardown restores the previous
    provider/instruments so metrics don't leak between tests.
    """
    reader = InMemoryMetricReader()
    restore = llm_observability.install_test_meter_provider(reader)
    try:
        yield reader
    finally:
        restore()


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """Yield an :class:`InMemorySpanExporter` wired into the global tracer provider.

    Spans finished while the fixture is active are captured (``SimpleSpanProcessor`` exports
    synchronously on span end). Teardown shuts the exporter down and detaches the processor so the
    global provider is left exactly as it was found.
    """
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), (
        "configure_observability() should install an SDK TracerProvider as the global provider"
    )
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    try:
        yield exporter
    finally:
        exporter.shutdown()
        multi = provider._active_span_processor
        with multi._lock:
            multi._span_processors = tuple(p for p in multi._span_processors if p is not processor)
