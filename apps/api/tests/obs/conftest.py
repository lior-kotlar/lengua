"""Fixtures for the observability tests (Phase 1.7).

:func:`span_exporter` attaches an in-memory span exporter to the **global** SDK tracer provider
that :func:`app.main.create_app` installs — so the tests assert against the real wiring rather
than a bespoke provider — and removes it again at teardown so spans don't leak between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Importing app.main runs the module-level ``app = create_app()``, which calls
# configure_observability() and installs the global SDK TracerProvider these fixtures rely on.
import app.main  # noqa: F401


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
