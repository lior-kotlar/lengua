"""Task 5.1.1 verify: every OTel signal is tagged ``service.name`` + ``deployment.environment``.

``test_request_span_carries_service_name_and_deployment_environment`` drives a real ``GET /health``
through ``create_app()`` and asserts the captured server span's **resource** carries
``service.name=lengua-api`` and a ``deployment.environment`` matching the resolved env. The
remaining tests prove the ``deployment.environment`` value flows from ``DEPLOYMENT_ENVIRONMENT``
(falling back to ``ENV``, default ``local``) by rebuilding a provider with the env var set, and
unit-test the resolver's branches directly.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.observability import (
    DEFAULT_SERVICE_NAME,
    _build_tracer_provider,
    _deployment_environment,
    build_resource,
)


def test_request_span_carries_service_name_and_deployment_environment(
    span_exporter: InMemorySpanExporter,
) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    spans = span_exporter.get_finished_spans()
    assert spans, "expected at least one span from the request"
    resource = dict(spans[0].resource.attributes)
    # Locked service name + the env tag, applied to real request spans via the global provider.
    assert resource["service.name"] == DEFAULT_SERVICE_NAME == "lengua-api"
    assert resource["deployment.environment"] == _deployment_environment()
    assert isinstance(resource["deployment.environment"], str)
    assert resource["deployment.environment"]


def _resource_of_one_span(provider: TracerProvider) -> Mapping[str, object]:
    """Emit and capture one span from ``provider``; return its resource attributes."""
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        provider.get_tracer("test").start_span("probe").end()
        spans = exporter.get_finished_spans()
        assert spans
        return dict(spans[0].resource.attributes)
    finally:
        provider.shutdown()


def test_deployment_environment_from_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # No OTLP endpoint -> the rebuilt provider stays a no-op exporter (zero network egress).
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")

    resource = _resource_of_one_span(_build_tracer_provider())
    assert resource["service.name"] == "lengua-api"
    assert resource["deployment.environment"] == "staging"


def test_deployment_environment_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.setenv("ENV", "prod")

    resource = _resource_of_one_span(_build_tracer_provider())
    assert resource["deployment.environment"] == "prod"


def test_deployment_environment_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    # DEPLOYMENT_ENVIRONMENT wins over ENV …
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("ENV", "prod")
    assert _deployment_environment() == "staging"
    # … then ENV is the fallback …
    monkeypatch.delenv("DEPLOYMENT_ENVIRONMENT", raising=False)
    assert _deployment_environment() == "prod"
    # … and "local" is the default when neither is set.
    monkeypatch.delenv("ENV", raising=False)
    assert _deployment_environment() == "local"


def test_build_resource_is_shared_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # The shared resource (used by BOTH the tracer and the cost-guard meter) carries exactly the
    # two attribution keys this task adds, so traces and metrics line up per environment.
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.setenv("ENV", "staging")

    attrs = dict(build_resource().attributes)
    assert attrs["service.name"] == "lengua-api"
    assert attrs["deployment.environment"] == "staging"
