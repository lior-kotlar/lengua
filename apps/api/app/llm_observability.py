"""Per-LLM-call observability: spans + metrics for the cost guard (Phase 3.8).

Every gated LLM operation emits one OpenTelemetry **span** (``llm.call``) carrying the cost-guard
context, and increments a small set of **metrics**, so budget burn and cap hits are visible before
they become a problem (rolled up into the Phase 5 dashboards).

**Span** (started by :class:`app.quota.QuotaGuard`, attributes set across the gate + the provider
boundary):

* ``quota.kind`` — ``generate`` / ``discover`` / ``explain``;
* ``quota.cap_hit`` — which gate blocked (``email`` / ``rate`` / ``daily_cap`` / ``global_budget``)
  or ``none`` when the call was admitted;
* ``budget.remaining`` — ``GLOBAL_DAILY_BUDGET - llm_budget[today]``;
* ``llm.provider`` / ``llm.model`` / ``llm.latency_ms`` / ``llm.tokens_in`` / ``llm.tokens_out`` —
  set at the provider call boundary (:func:`app.llm_runner.run_provider`). A *blocked* call never
  reaches the provider, so it records tokens ``0`` and still emits a span.

**Metrics** (no-op unless an OTLP metrics endpoint is configured — same zero-egress discipline as
the tracer):

* ``llm_calls_total{kind, result}`` — counter; ``result`` ∈ ``success`` / ``blocked`` / ``error``;
* ``llm_cap_hits_total{gate}`` — counter, incremented when a gate blocks a call;
* ``llm_budget_remaining`` — an observable gauge reporting the latest
  ``GLOBAL_DAILY_BUDGET - llm_budget[today]``.

The :class:`~opentelemetry.sdk.metrics.MeterProvider` is **owned here** (not the OTel global) and
built lazily: with no ``OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`` (or the generic ``…_OTLP_ENDPOINT``)
set it has *no* metric readers, so measurements are dropped — prod/CI stay no-op with zero network.
It carries the **same** resource (``service.name`` + ``deployment.environment``) as the tracer via
:func:`app.observability.build_resource`, so metrics and traces are attributed consistently per
environment (task 5.1.1). Tests swap in an in-memory reader via :func:`install_test_meter_provider`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.metrics import CallbackOptions, Counter, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.trace import Span

from app.observability import build_resource

# ── Span name + attribute keys (one constant per attribute so the guard, the provider boundary,
#    and the tests all reference the same string) ────────────────────────────────────────────────
LLM_SPAN_NAME = "llm.call"

ATTR_LLM_PROVIDER = "llm.provider"
ATTR_LLM_MODEL = "llm.model"
ATTR_LLM_LATENCY_MS = "llm.latency_ms"
ATTR_LLM_TOKENS_IN = "llm.tokens_in"
ATTR_LLM_TOKENS_OUT = "llm.tokens_out"
ATTR_QUOTA_KIND = "quota.kind"
ATTR_QUOTA_CAP_HIT = "quota.cap_hit"
ATTR_BUDGET_REMAINING = "budget.remaining"

#: ``quota.cap_hit`` value for an admitted (un-blocked) call.
CAP_HIT_NONE = "none"

# ── Metric / result vocab ───────────────────────────────────────────────────────────────────────
RESULT_SUCCESS = "success"
RESULT_BLOCKED = "blocked"
RESULT_ERROR = "error"

_tracer = trace.get_tracer("lengua.llm")


def start_llm_span(kind: str) -> Span:
    """Start (but do not make current) the per-call ``llm.call`` span, stamped with ``quota.kind``.

    Parented under whatever span is current (the FastAPI server span during a request), so it nests
    in the request trace. The caller owns the span's lifecycle (attributes + ``end()``).
    """
    span = _tracer.start_span(LLM_SPAN_NAME)
    span.set_attribute(ATTR_QUOTA_KIND, kind)
    return span


# ── Metrics: a lazily-built, module-owned MeterProvider (no-op unless an endpoint is set) ─────────


def _otlp_metrics_endpoint() -> str | None:
    """The configured OTLP metrics endpoint, if any (standard OpenTelemetry env vars)."""
    return os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )


def _build_meter_provider() -> MeterProvider:
    """Build a :class:`MeterProvider`, attaching an OTLP metric reader only when an endpoint is set.

    With no endpoint configured the provider has **no** metric readers, so recorded measurements
    are dropped — zero network egress, the no-op path used by local dev and CI. When an endpoint is
    set a periodic OTLP exporter is attached (it reads endpoint/headers/protocol from the standard
    ``OTEL_EXPORTER_OTLP_*`` env vars).
    """
    readers: list[MetricReader] = []
    if _otlp_metrics_endpoint():
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
    # Same resource (service.name + deployment.environment) as the tracer, so metrics and traces
    # carry identical attribution per environment (task 5.1.1).
    return MeterProvider(metric_readers=readers, resource=build_resource())


@dataclass
class _Instruments:
    """The cost-guard metric instruments, bound to one meter."""

    calls_total: Counter
    cap_hits_total: Counter


# The latest ``GLOBAL_DAILY_BUDGET - llm_budget[today]``, surfaced by the observable gauge. ``None``
# until the first budget read/accounted call, so the gauge reports nothing before any LLM traffic.
_budget_remaining: int | None = None

_meter_provider: MeterProvider | None = None
_instruments: _Instruments | None = None


def _observe_budget_remaining(options: CallbackOptions) -> Iterable[Observation]:
    """ObservableGauge callback: report the latest budget-remaining value (none until first set)."""
    if _budget_remaining is not None:
        yield Observation(_budget_remaining)


def _get_instruments() -> _Instruments:
    """Return the metric instruments, building the meter provider + instruments on first use."""
    global _meter_provider, _instruments
    if _instruments is None:
        if _meter_provider is None:
            _meter_provider = _build_meter_provider()
        meter = _meter_provider.get_meter("lengua.llm")
        meter.create_observable_gauge(
            "llm_budget_remaining",
            callbacks=[_observe_budget_remaining],
            description="Remaining global LLM daily budget (GLOBAL_DAILY_BUDGET - today's count).",
        )
        _instruments = _Instruments(
            calls_total=meter.create_counter(
                "llm_calls_total",
                description="LLM calls by kind and result (success / blocked / error).",
            ),
            cap_hits_total=meter.create_counter(
                "llm_cap_hits_total",
                description="LLM calls blocked by a cost-guard gate, by which gate.",
            ),
        )
    return _instruments


def record_call(kind: str, result: str) -> None:
    """Increment ``llm_calls_total{kind, result}`` (result ∈ success / blocked / error)."""
    _get_instruments().calls_total.add(1, {"kind": kind, "result": result})


def record_cap_hit(gate: str) -> None:
    """Increment ``llm_cap_hits_total{gate}`` — one gate blocked one call."""
    _get_instruments().cap_hits_total.add(1, {"gate": gate})


def set_budget_remaining(value: int) -> None:
    """Update the value the ``llm_budget_remaining`` observable gauge reports on next collection."""
    global _budget_remaining
    _budget_remaining = value


def peek_budget_remaining(default: int) -> int:
    """The last-known remaining budget, or ``default`` when none has been observed yet.

    Lets a span for a call blocked by an *earlier* gate (email / rate / daily-cap, which never read
    the global budget) still carry a sensible ``budget.remaining`` without an extra privileged DB
    read on the fast-fail path.
    """
    return _budget_remaining if _budget_remaining is not None else default


def install_test_meter_provider(reader: InMemoryMetricReader) -> Callable[[], None]:
    """Swap in a meter provider whose only reader is ``reader`` (tests); return a restore callable.

    Resets the cached instruments so they rebuild against ``reader`` (re-registering the observable
    gauge), and clears the gauge's backing value for test isolation. The returned callable restores
    the previous provider/instruments/value and shuts the test provider down.
    """
    global _meter_provider, _instruments, _budget_remaining
    prev_provider, prev_instruments, prev_remaining = (
        _meter_provider,
        _instruments,
        _budget_remaining,
    )
    _meter_provider = MeterProvider(
        metric_readers=[reader],
        resource=Resource.create({SERVICE_NAME: "lengua-api-test"}),
    )
    _instruments = None
    _budget_remaining = None
    _get_instruments()  # build eagerly so the gauge is registered (and ``reader`` collects) at once

    def _restore() -> None:
        global _meter_provider, _instruments, _budget_remaining
        assert _meter_provider is not None
        _meter_provider.shutdown()
        _meter_provider = prev_provider
        _instruments = prev_instruments
        _budget_remaining = prev_remaining

    return _restore
