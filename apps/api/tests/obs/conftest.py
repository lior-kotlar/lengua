"""Fixtures for the observability tests (Phase 1.7 + 3.8).

:func:`span_exporter` attaches an in-memory span exporter to the **global** SDK tracer provider
that :func:`app.main.create_app` installs — so the tests assert against the real wiring rather
than a bespoke provider — and removes it again at teardown so spans don't leak between tests.

:func:`metric_reader` swaps the cost-guard's module-owned :class:`MeterProvider` (``app
.llm_observability``) for one whose only reader is an in-memory reader, so the LLM metrics
(task 3.8.2) can be collected and asserted, restoring the previous provider at teardown.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Importing app.main runs the module-level ``app = create_app()``, which calls
# configure_observability() and installs the global SDK TracerProvider these fixtures rely on.
import app.main  # noqa: F401
from app import llm_observability, product_metrics


def counter_value(reader: InMemoryMetricReader, name: str, attrs: Mapping[str, str]) -> int:
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


def sum_counter(reader: InMemoryMetricReader, name: str) -> int:
    """The total across every data point of counter ``name`` (0 when it has recorded nothing)."""
    data = reader.get_metrics_data()
    total = 0
    if data is None:
        return total
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    total += sum(int(dp.value) for dp in metric.data.data_points)
    return total


def gauge_values(reader: InMemoryMetricReader, name: str) -> list[float]:
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
def reset_product_state() -> Iterator[None]:
    """Clear the process-local product trackers (active users + signup dedup) around a test.

    The product counters reset with the swapped :func:`metric_reader` provider, but the active-user
    window and the "first seen" signup dedup are plain module state, so other tests' activity would
    otherwise leak in. Clearing on entry and exit keeps the product-metric assertions deterministic.
    """
    product_metrics.reset_product_metrics_state()
    try:
        yield
    finally:
        product_metrics.reset_product_metrics_state()


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
