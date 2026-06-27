"""Task 5.2.6 (CI half): the FastAPI instrumentation exports a per-route RED duration histogram.

The auto-instrumentation gives request rate / errors / latency per route "for free" once it is wired
to a ``MeterProvider``. ``configure_observability`` now passes the app-wide meter provider to
``FastAPIInstrumentor.instrument_app`` (task 5.2.6), so each request records an ``http.server``
duration **histogram** carrying a per-route label and the HTTP status. This drives one
``GET /health`` through a freshly-built app (so the FastAPI instrumentation binds the in-memory test
meter provider the ``metric_reader`` fixture installed) and asserts that histogram + route label are
emitted.

**Route-label reconciliation:** the pinned ``opentelemetry-instrumentation-fastapi`` (old HTTP
semconv) labels the server-duration histogram with ``http.target`` (the request path) rather than
``http.route`` (the template) — they coincide for a static path like ``/health``; the span still
carries ``http.route`` (5.1.2). We accept either label here; grouping the live per-route p95 by the
emitted label is the owner/Phase-6 query, logged in ``planning/outstanding-work.md`` §11.

The **live half** — querying the per-route p95 of this histogram in Grafana Explore against Mimir
after a load script — needs the Phase-6 staging deploy + Grafana creds (owner) and is logged there.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import Histogram, InMemoryMetricReader

from app.main import create_app

# The OTel ASGI/FastAPI instrumentation emits the server request-duration histogram under one of
# these names depending on the HTTP-semconv version.
_DURATION_HISTOGRAM_NAMES = frozenset({"http.server.duration", "http.server.request.duration"})
# …and the per-route label is ``http.route`` (template, stable semconv) or ``http.target`` (path,
# the old semconv this instrumentation emits). Either satisfies "RED metric carrying a route label".
_ROUTE_LABEL_KEYS = ("http.route", "http.target")


def _route_histogram_points(reader: InMemoryMetricReader) -> list[tuple[str, object]]:
    """Return ``(metric_name, route)`` for each duration-histogram data point with a route label."""
    data = reader.get_metrics_data()
    assert data is not None
    points: list[tuple[str, object]] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name not in _DURATION_HISTOGRAM_NAMES:
                    continue
                assert isinstance(metric.data, Histogram)
                for dp in metric.data.data_points:
                    attrs = dict(dp.attributes or {})
                    route = next((attrs[k] for k in _ROUTE_LABEL_KEYS if k in attrs), None)
                    if route is not None:
                        points.append((metric.name, route))
    return points


def test_fastapi_emits_per_route_duration_histogram(metric_reader: InMemoryMetricReader) -> None:
    # Build the app AFTER the in-memory meter provider is installed, so instrument_app binds it and
    # the request-duration histogram is collected by ``metric_reader``.
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    points = _route_histogram_points(metric_reader)
    assert points, "expected a FastAPI request-duration histogram with a per-route label"
    names = {name for name, _ in points}
    assert names & _DURATION_HISTOGRAM_NAMES, f"unexpected histogram metric names: {names}"
    assert any(route == "/health" for _, route in points), (
        f"expected a /health route series; got {points}"
    )
