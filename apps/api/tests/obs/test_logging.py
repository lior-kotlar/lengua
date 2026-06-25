"""Task 1.7.2 verify: one structured JSON log line per request with a trace_id for correlation.

``test_request_emits_structured_json_log`` captures the access-log line for a real ``GET /health``,
parses it as JSON, and asserts ``method`` / ``status`` / ``latency_ms`` and a ``trace_id`` key are
present — and that the ``trace_id`` matches the request's server span (proving log<->trace
correlation). The remaining tests cover the formatter's extra-field/exception handling and the
``current_trace_id`` no-span path.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.observability import (
    REQUEST_LOGGER_NAME,
    JsonLogFormatter,
    current_trace_id,
)


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

    # trace_id is the active server span's id (32 hex chars) — logs correlate with traces.
    server_spans = [
        s for s in span_exporter.get_finished_spans() if s.kind == trace.SpanKind.SERVER
    ]
    assert server_spans
    assert record["trace_id"] == format(server_spans[0].context.trace_id, "032x")
    assert len(record["trace_id"]) == 32


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
