"""Task 1.7.1 verify: OpenTelemetry is wired so a request emits an HTTP server span.

``test_health_request_emits_http_server_span`` drives one ``GET /health`` through the real
``create_app()`` wiring and asserts an HTTP **server** span reached an in-memory exporter. The
remaining tests cover the provider construction (no-op when no OTLP endpoint is configured, OTLP
exporter attached when one is) and that all three instrumentations are active.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.observability import _build_tracer_provider


def test_health_request_emits_http_server_span(span_exporter: InMemorySpanExporter) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200

    spans = span_exporter.get_finished_spans()
    server_spans = [s for s in spans if s.kind == trace.SpanKind.SERVER]
    assert server_spans, f"expected an HTTP server span; got kinds {[s.kind for s in spans]}"
    # The FastAPI instrumentation names the server span after the matched route.
    assert any("/health" in (s.name or "") for s in server_spans)


def test_build_tracer_provider_is_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    provider = _build_tracer_provider()
    try:
        # No exporter attached -> spans are created by instrumentation but dropped (no egress).
        assert provider._active_span_processor._span_processors == ()
    finally:
        provider.shutdown()


def test_build_tracer_provider_attaches_otlp_exporter_with_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    provider = _build_tracer_provider()
    try:
        processors = provider._active_span_processor._span_processors
        assert len(processors) == 1
        assert isinstance(processors[0], BatchSpanProcessor)
    finally:
        provider.shutdown()  # stops the batch worker + closes the (never-connected) exporter


def test_fastapi_sqlalchemy_httpx_are_instrumented() -> None:
    app = create_app()
    # FastAPI is instrumented per-app (instrument_app sets a flag on the app instance, not on the
    # global instrumentor); httpx + SQLAlchemy are instrumented process-globally. That FastAPI
    # instrumentation actually emits spans is proven by test_health_request_emits_http_server_span.
    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is True
    assert HTTPXClientInstrumentor().is_instrumented_by_opentelemetry
    assert SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry
