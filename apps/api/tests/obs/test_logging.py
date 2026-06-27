"""Task 1.7.2 / 5.3.1 verify: one structured JSON access line per request + OTLP log export wiring.

``test_request_emits_structured_json_log`` captures the access-log line for a real ``GET /health``,
parses it as JSON (the 5.3.1 "valid JSON" check), and asserts ``method`` / ``status`` /
``latency_ms`` plus the correlation ids (``trace_id`` / ``span_id`` matching the request's server
span; ``user_id`` ``None`` on the access line, which is emitted in the outer ASGI context). The
``logger_provider`` tests cover the OTel :class:`LoggerProvider` wiring (no-op without an OTLP logs
endpoint, OTLP exporter attached with one), that ``configure_observability`` attaches the
:class:`LoggingHandler` to the root + access loggers, and that records routed through that handler
actually reach an exporter. The rest cover the formatter and the ``current_trace_id`` no-span path.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.observability import (
    REQUEST_LOGGER_NAME,
    JsonLogFormatter,
    TraceCorrelationFilter,
    _build_logger_provider,
    current_trace_id,
    get_logger_provider,
)
from app.request_context import set_current_user_id


@pytest.fixture
def captured_access_log() -> Iterator[io.StringIO]:
    """Attach a JSON-formatting handler to the request logger and capture its output."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger(REQUEST_LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


def test_request_emits_structured_json_log(
    captured_access_log: io.StringIO, span_exporter: InMemorySpanExporter
) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200

    lines = [line for line in captured_access_log.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one access-log line, got {lines!r}"
    record = json.loads(lines[0])  # must parse as JSON

    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["status"] == 200
    assert isinstance(record["latency_ms"], (int, float))
    assert record["latency_ms"] >= 0
    assert "trace_id" in record

    # trace_id + span_id are the active server span's ids — logs correlate with traces (5.3.2).
    server_spans = [
        s for s in span_exporter.get_finished_spans() if s.kind == trace.SpanKind.SERVER
    ]
    assert server_spans
    assert record["trace_id"] == format(server_spans[0].context.trace_id, "032x")
    assert len(record["trace_id"]) == 32
    assert record["span_id"] == format(server_spans[0].context.span_id, "016x")
    # /health is unauthenticated and the access line is emitted in the outer ASGI context, so the
    # per-request user-id contextvar (set by the auth dependency in the inner task) is not visible.
    assert "user_id" in record
    assert record["user_id"] is None


def test_json_formatter_merges_extras_and_exception() -> None:
    formatter = JsonLogFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="lengua.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="oops",
            args=None,
            exc_info=sys.exc_info(),
        )
    record.custom_field = "value"  # a structured extra

    out = json.loads(formatter.format(record))

    assert out["level"] == "ERROR"
    assert out["logger"] == "lengua.test"
    assert out["message"] == "oops"
    assert out["custom_field"] == "value"
    assert "ValueError: boom" in out["exc_info"]
    assert "timestamp" in out


def test_current_trace_id_is_none_without_active_span() -> None:
    assert current_trace_id() is None


# ── 5.3.1: OTel LoggerProvider + OTLP log export wiring ───────────────────────────────────────────


def test_logger_provider_is_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """No OTLP logs endpoint -> the provider has no processors, so records drop (zero egress)."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)

    provider = _build_logger_provider()
    try:
        assert provider._multi_log_record_processor._log_record_processors == ()
    finally:
        provider.shutdown()


def test_logger_provider_attaches_otlp_exporter_with_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic OTLP endpoint var attaches one batching OTLP log-record processor."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    provider = _build_logger_provider()
    try:
        processors = provider._multi_log_record_processor._log_record_processors
        assert len(processors) == 1
        assert isinstance(processors[0], BatchLogRecordProcessor)
    finally:
        provider.shutdown()  # stops the batch worker + closes the (never-connected) exporter


def test_logs_specific_endpoint_attaches_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs-specific OTLP endpoint var alone also attaches the batch log exporter (5.3.1)."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:4317")

    provider = _build_logger_provider()
    try:
        processors = provider._multi_log_record_processor._log_record_processors
        assert len(processors) == 1
        assert isinstance(processors[0], BatchLogRecordProcessor)
    finally:
        provider.shutdown()


def test_get_logger_provider_is_cached() -> None:
    """The module-owned provider is built once and reused (idempotent)."""
    assert get_logger_provider() is get_logger_provider()


def test_configure_observability_wires_otel_log_handler() -> None:
    """create_app() attaches the OTel LoggingHandler (bound to the module provider) to root+access.

    The handler exports stdlib logs through OTel; here we just assert it is wired (no endpoint set).
    """
    create_app()  # idempotent; the import-time create_app already configured logging

    provider = get_logger_provider()
    root_handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, LoggingHandler) and h._logger_provider is provider
    ]
    access_handlers = [
        h
        for h in logging.getLogger(REQUEST_LOGGER_NAME).handlers
        if isinstance(h, LoggingHandler) and h._logger_provider is provider
    ]
    # Exactly one each (the idempotency guard prevents stacking across repeated create_app() calls).
    assert len(root_handlers) == 1
    assert len(access_handlers) == 1


def test_otel_log_export_routes_records_to_exporter() -> None:
    """A record routed through the OTel LoggingHandler reaches the exporter, with user_id (5.3.1).

    Builds the same handler shape ``configure_observability`` installs (a ``LoggingHandler`` +
    ``TraceCorrelationFilter``) but over an in-memory exporter, then logs inside an active span with
    the user-id contextvar set and asserts the exported record carries the message, the correlated
    trace id, and ``user_id`` as an attribute.
    """
    exporter = InMemoryLogExporter()
    provider = LoggerProvider(resource=Resource.create({SERVICE_NAME: "lengua-api-test"}))
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)
    handler.addFilter(TraceCorrelationFilter())

    logger = logging.getLogger("lengua.test.otlp_export")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    user_id = uuid.uuid4()
    set_current_user_id(user_id)
    try:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("unit") as span:
            span_context = span.get_span_context()
            logger.info("exported line")
        provider.force_flush()

        logs = exporter.get_finished_logs()
        assert len(logs) == 1
        emitted = logs[0].log_record
        assert emitted.body == "exported line"
        # The OTel LoggingHandler stamps the active trace id onto the exported record itself...
        assert emitted.trace_id == span_context.trace_id
        # ...and our filter's user_id rides along as a log attribute (so Loki can filter by it).
        assert (emitted.attributes or {}).get("user_id") == str(user_id)
    finally:
        set_current_user_id(None)
        logger.removeHandler(handler)
        provider.shutdown()
