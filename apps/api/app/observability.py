"""OpenTelemetry tracing + structured JSON request logging (Phase 1.7).

:func:`configure_observability` is called from :func:`app.main.create_app` and wires the
instrumentation hooks the roadmap starts here (dashboards/alerts land in Phase 5):

* a process-wide OpenTelemetry :class:`~opentelemetry.sdk.trace.TracerProvider` whose resource
  tags every signal with ``service.name`` (from ``OTEL_SERVICE_NAME``, default ``lengua-api``) and
  ``deployment.environment`` (from ``DEPLOYMENT_ENVIRONMENT`` / ``ENV``, default ``local``) — the
  same :func:`build_resource` is shared with the cost-guard ``MeterProvider``
  (:mod:`app.llm_observability`) so traces and metrics are attributed consistently per environment —
  and that **only** attaches an OTLP span exporter when ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or the
  traces-specific variant) is set, so local dev and CI are a no-op with zero network egress;
* auto-instrumentation for **FastAPI** (HTTP server spans, per app), **SQLAlchemy** (DB query
  spans), and **httpx** (outbound client spans);
* a middleware that emits exactly one structured JSON access-log line per request
  (``method`` / ``path`` / ``status`` / ``latency_ms``) carrying the active ``trace_id`` so logs
  correlate with traces; and
* (task 5.3) a module-owned OTel :class:`~opentelemetry.sdk._logs.LoggerProvider` + a
  :class:`~opentelemetry.sdk._logs.LoggingHandler` routing stdlib logging through OTel so records
  can export to Loki — attached to the root and access loggers, sharing :func:`build_resource`, and
  (like the tracer/meter) a no-op with zero egress unless an OTLP logs endpoint is set. A
  :class:`TraceCorrelationFilter` stamps ``trace_id`` / ``span_id`` / ``user_id`` onto every record
  (task 5.3.2) so each log line — stdout JSON and OTLP — joins to its trace.

The OTLP endpoint, headers, and protocol are read from the standard ``OTEL_EXPORTER_OTLP_*``
environment variables — the exporter picks them up itself, so wiring a real backend in Phase 5 is
a config change, never a code change.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.request_context import get_current_user_id

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Logger carrying the one-line-per-request structured access log.
REQUEST_LOGGER_NAME = "lengua.access"

#: Default OpenTelemetry ``service.name`` (overridable via ``OTEL_SERVICE_NAME``).
DEFAULT_SERVICE_NAME = "lengua-api"

#: Default ``deployment.environment`` resource tag when neither ``DEPLOYMENT_ENVIRONMENT`` nor the
#: app's ``ENV`` is set. The documented allowed values are ``local`` | ``staging`` | ``prod`` (kept
#: as a free string — not hard-validated — to mirror ``app.settings.Settings.env``).
DEFAULT_DEPLOYMENT_ENVIRONMENT = "local"

_request_logger = logging.getLogger(REQUEST_LOGGER_NAME)

# Module-level guards so repeated create_app() calls (the tests, the module-level app) don't
# re-instrument the global libraries or stack duplicate log handlers.
_globally_instrumented = False
_logging_configured = False
_otel_log_export_configured = False

# The module-owned OTel LoggerProvider (task 5.3.1), built lazily — mirrors the cost-guard
# MeterProvider (app.llm_observability): it is NOT the OTel global, and it has no log-record
# processors unless an OTLP logs endpoint is configured, so local/CI stay no-op with zero egress.
_logger_provider: LoggerProvider | None = None

# Standard LogRecord attributes; everything else on a record is a structured "extra" and is
# merged into the JSON payload as a top-level key (so the middleware's method/path/status/... and
# any future ``extra=`` fields show up without per-field wiring).
_STD_LOGRECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single line of JSON.

    Base fields (``timestamp``, ``level``, ``logger``, ``message``) are always present; structured
    values passed via ``logging``'s ``extra=`` (the per-request ``method`` / ``status`` /
    ``latency_ms`` / ``trace_id``) are merged in as top-level keys.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD_LOGRECORD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def current_trace_id() -> str | None:
    """The active span's 32-hex trace id, or ``None`` when no recording span is active.

    Stamped on every access-log line so logs correlate with traces. Because the logging
    middleware runs *inside* the FastAPI server span (the OTel ASGI middleware is always the
    outermost layer), this is a real OpenTelemetry trace id during a request and ``None`` outside
    one.
    """
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


class TraceCorrelationFilter(logging.Filter):
    """Stamp every log record with the active trace/span ids and the request's user id (task 5.3.2).

    Attached to the access-log stdout handler and the OTLP :class:`LoggingHandler`, so each emitted
    record carries:

    * ``trace_id`` (32 hex) / ``span_id`` (16 hex) — from the active OpenTelemetry span, or ``None``
      when no recording span is active (outside a request); and
    * ``user_id`` — the authenticated user's id from the per-request contextvar
      (:func:`app.request_context.get_current_user_id`), set where ``current_user`` resolves;
      ``None`` when unauthenticated/unavailable (e.g. the access line, emitted in the outer task).

    Each field is written with ``setdefault`` so an explicit ``extra=`` value already on the record
    (e.g. the access line's own ``trace_id``) is preserved. The filter never drops a record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            trace_id: str | None = format(span_context.trace_id, "032x")
            span_id: str | None = format(span_context.span_id, "016x")
        else:
            trace_id = span_id = None
        user_id = get_current_user_id()
        # Write into __dict__ (where logging stores `extra=` fields) so the JSON formatter and the
        # OTLP LoggingHandler both pick them up; setdefault preserves any explicitly-passed value.
        record.__dict__.setdefault("trace_id", trace_id)
        record.__dict__.setdefault("span_id", span_id)
        record.__dict__.setdefault("user_id", str(user_id) if user_id is not None else None)
        return True


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured JSON log line per HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        _request_logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "trace_id": current_trace_id(),
            },
        )
        return response


def _otlp_endpoint() -> str | None:
    """The configured OTLP traces endpoint, if any (standard OpenTelemetry env vars)."""
    return os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )


def _deployment_environment() -> str:
    """The ``deployment.environment`` resource tag for every OTel signal (task 5.1.1).

    Read from ``DEPLOYMENT_ENVIRONMENT``, falling back to ``ENV`` (the same variable
    :attr:`app.settings.Settings.env` reads), defaulting to ``local``. Read straight from the
    process environment (not via ``Settings``) so this module stays decoupled from the settings
    machinery, exactly like the ``OTEL_*`` vars above. Documented allowed values: ``local`` |
    ``staging`` | ``prod``.
    """
    return os.getenv("DEPLOYMENT_ENVIRONMENT") or os.getenv("ENV") or DEFAULT_DEPLOYMENT_ENVIRONMENT


def build_resource() -> Resource:
    """The OpenTelemetry :class:`~opentelemetry.sdk.resources.Resource` shared by all signals.

    Tags every span and metric with ``service.name`` (``OTEL_SERVICE_NAME``, default ``lengua-api``)
    and ``deployment.environment`` (see :func:`_deployment_environment`). Applied to **both** the
    :class:`TracerProvider` here and the cost-guard ``MeterProvider`` in
    :mod:`app.llm_observability`, so traces and metrics carry identical attribution per environment
    (task 5.1.1).
    """
    return Resource.create(
        {
            SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            DEPLOYMENT_ENVIRONMENT: _deployment_environment(),
        }
    )


def _build_tracer_provider() -> TracerProvider:
    """Build a :class:`TracerProvider`, attaching an OTLP exporter only when an endpoint is set.

    With no endpoint configured the provider has no span processors: instrumentation still creates
    spans but they are dropped, so there is zero network egress (the no-op path used by local dev
    and CI). When an endpoint is set, a batching OTLP exporter is attached; it reads the endpoint,
    headers, and protocol from the standard ``OTEL_EXPORTER_OTLP_*`` environment variables.
    """
    provider = TracerProvider(resource=build_resource())
    if _otlp_endpoint():
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def _ensure_tracer_provider() -> TracerProvider:
    """Return the global SDK tracer provider, installing one on first use (idempotent)."""
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = _build_tracer_provider()
    trace.set_tracer_provider(provider)
    return provider


def _otlp_logs_endpoint() -> str | None:
    """The configured OTLP logs endpoint, if any (standard OpenTelemetry env vars)."""
    return os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def _build_logger_provider() -> LoggerProvider:
    """Build a :class:`LoggerProvider`, attaching an OTLP log exporter only when an endpoint is set.

    Mirrors :func:`_build_tracer_provider`: with no endpoint the provider has no log-record
    processors, so records routed through the OTel :class:`LoggingHandler` are dropped (zero network
    egress — the no-op path for local dev and CI). When an endpoint is set a batching OTLP log
    exporter is attached; it reads the endpoint, headers, and protocol from the standard
    ``OTEL_EXPORTER_OTLP_*`` environment variables. Carries the same :func:`build_resource`
    (``service.name`` + ``deployment.environment``) as the tracer/meter so Loki can filter logs by
    ``service_name="lengua-api"`` consistently with traces and metrics (task 5.3.1).
    """
    provider = LoggerProvider(resource=build_resource())
    if _otlp_logs_endpoint():
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

        provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    return provider


def get_logger_provider() -> LoggerProvider:
    """The module-owned OTel :class:`LoggerProvider`, built lazily on first use (idempotent)."""
    global _logger_provider
    if _logger_provider is None:
        _logger_provider = _build_logger_provider()
    return _logger_provider


def _instrument_globals(provider: TracerProvider) -> None:
    """Auto-instrument httpx + SQLAlchemy once (process-global, so guarded against repeats).

    SQLAlchemy is instrumented with no specific engine, so the wrapper covers any engine created
    afterwards — the app's async engine is built lazily on first DB use.
    """
    global _globally_instrumented
    if _globally_instrumented:
        return
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(tracer_provider=provider)
    _globally_instrumented = True


def _configure_request_logging() -> None:
    """Attach a JSON stdout handler to the request logger once (idempotent)."""
    global _logging_configured
    if _logging_configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(TraceCorrelationFilter())  # stamp trace_id/span_id/user_id (task 5.3.2)
    _request_logger.addHandler(handler)
    _request_logger.setLevel(logging.INFO)
    _request_logger.propagate = False  # this handler owns the access lines; don't double-log
    _logging_configured = True


def _configure_otel_log_export() -> None:
    """Route stdlib logging through OTel so records can export to Loki (task 5.3.1), once.

    Attaches one :class:`LoggingHandler` (bound to the module-owned :func:`get_logger_provider`, and
    carrying the :class:`TraceCorrelationFilter` so exported records keep ``user_id`` — the handler
    itself stamps ``trace_id`` / ``span_id`` from the active span) to:

    * the **root** logger — so application/library log records that propagate there are exported;
      and
    * the **access** logger — which has ``propagate=False`` (it owns its stdout line), so it would
      otherwise never reach the root handler.

    The existing stdout JSON line is kept (Cloud Run ships stdout to Loki as the primary path; this
    OTLP export is the direct-to-Loki alternative). With no OTLP logs endpoint the provider has no
    processors, so this is a no-op with zero egress (the local/CI path).
    """
    global _otel_log_export_configured
    if _otel_log_export_configured:
        return
    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=get_logger_provider())
    otel_handler.addFilter(TraceCorrelationFilter())
    logging.getLogger().addHandler(otel_handler)
    _request_logger.addHandler(otel_handler)
    _otel_log_export_configured = True


def configure_observability(app: FastAPI) -> None:
    """Wire OpenTelemetry tracing + structured request logging into ``app``.

    Idempotent across multiple ``create_app()`` calls: the global tracer provider, the httpx /
    SQLAlchemy instrumentation, and the JSON log handler are each installed once; FastAPI is
    instrumented per app instance (its own guard prevents double-instrumentation). The OTel ASGI
    middleware ends up outermost (FastAPI instrumentation rebuilds the middleware stack), so the
    request-logging middleware runs inside the active server span and can stamp its ``trace_id``.

    The FastAPI instrumentation is also given the app-wide ``MeterProvider`` (task 5.2.6) so it
    emits the per-route RED histogram (``http.server.duration`` with an ``http.route`` label): rate,
    errors, and p50/p95/p99 latency for free. The provider is imported lazily here to avoid an
    import cycle (``app.llm_observability`` imports :func:`build_resource` from here); with no OTLP
    metrics endpoint it has no readers, so the histogram is recorded into a no-op (zero egress).
    """
    from app.llm_observability import get_meter_provider

    _configure_request_logging()
    _configure_otel_log_export()
    provider = _ensure_tracer_provider()
    app.add_middleware(RequestLoggingMiddleware)
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, meter_provider=get_meter_provider()
    )
    _instrument_globals(provider)
