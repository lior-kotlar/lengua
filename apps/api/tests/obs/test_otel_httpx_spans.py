"""Task 5.1.4 verify: outbound httpx calls become CLIENT spans nested under the active span.

A real outbound ``httpx`` request to a controlled **loopback** HTTP server (no external network)
produces an httpx CLIENT span that nests under the active parent span — proving the httpx
auto-instrumentation wired in :func:`app.observability.configure_observability` works and propagates
context.

PROVIDER NOTE (why a loopback stub, not the LLM): under the deterministic ``FakeLLM`` used in all
dev/CI/E2E the provider call is **in-process** and makes **no** outbound httpx request, so a
generate trace has no provider httpx span — its in-process provider-call signal is the custom
``llm.call`` span (group 5.2 / task 3.8). In prod the real Groq/Gemini HTTP client makes the
outbound call and produces exactly this httpx CLIENT span under the request span — the path this
test exercises honestly with a local stub (an in-process ``ASGITransport`` is deliberately NOT used:
the httpx instrumentation wraps the real network transport, so an ASGI transport emits no span).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class _OkHandler(BaseHTTPRequestHandler):
    """Answer every GET with 200 ``ok`` and stay quiet (no stderr access logging)."""

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler dispatch name)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args: object) -> None:
        return None


@pytest.fixture
def loopback_url() -> Iterator[str]:
    """Run a throwaway loopback HTTP server in a background thread; yield its base URL."""
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_outbound_httpx_request_emits_nested_client_span(
    loopback_url: str, span_exporter: InMemorySpanExporter
) -> None:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent") as parent:
        with httpx.Client() as client:  # default (instrumented) transport -> real loopback request
            response = client.get(f"{loopback_url}/probe")
        parent_ctx = parent.get_span_context()
    assert response.status_code == 200

    client_spans = [
        s for s in span_exporter.get_finished_spans() if s.kind == trace.SpanKind.CLIENT
    ]
    assert len(client_spans) == 1, f"expected one httpx CLIENT span, got {len(client_spans)}"
    span = client_spans[0]

    attrs = dict(span.attributes or {})
    # Old vs new HTTP semconv — this instrumentation emits http.method / http.status_code.
    assert attrs.get("http.method", attrs.get("http.request.method")) == "GET"
    assert attrs.get("http.status_code", attrs.get("http.response.status_code")) == 200

    # Nested under the active span: same trace, parented directly to it.
    assert span.context.trace_id == parent_ctx.trace_id
    assert span.parent is not None
    assert span.parent.span_id == parent_ctx.span_id
