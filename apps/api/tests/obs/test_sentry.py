"""Task 5.4.1 verify: backend Sentry is DSN-gated and captures a debug error with correlation.

These cover :mod:`app.error_tracking` end-to-end:

* it is a **no-op with zero egress** unless ``SENTRY_DSN_API`` is set (mirroring the OTLP path);
* when enabled, ``environment`` is stamped from ``DEPLOYMENT_ENVIRONMENT`` and each request binds
  the ``user.id`` + a ``trace_id`` tag onto Sentry's isolation scope; and
* hitting the deliberately-failing test-only route ``GET /__test__/debug-error`` raises and a Sentry
  event is captured carrying that ``user_id`` + a ``trace_id`` (asserted via an in-memory transport,
  so there is zero network egress).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app import error_tracking
from app.error_tracking import configure_error_tracking, is_enabled, sentry_dsn
from app.main import create_app
from app.settings import Settings
from tests.auth_helpers import auth_header, install_test_auth

USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000004a1")
STUB_DSN = "https://public@example.invalid/1"


class MemoryTransport(Transport):
    """A Sentry transport that records events in memory and never touches the network."""

    def __init__(self) -> None:
        super().__init__()
        # Sentry's Event is a TypedDict; keep these as plain mappings for ergonomic assertions.
        self.events: list[Any] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self.events.append(event)


def _stub_settings(dsn: str = STUB_DSN) -> Settings:
    """Settings carrying a Sentry DSN (and nothing else of note) for the enabled-path tests."""
    return Settings(_env_file=None, sentry_dsn_api=dsn)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _reset_sentry() -> Any:
    """Disable Sentry after every test here so init never leaks into the rest of the suite."""
    yield
    error_tracking._reset_for_tests()


# ── DSN gating (no-op unless configured) ──────────────────────────────────────────────────────────


def test_sentry_dsn_reads_and_blanks() -> None:
    assert sentry_dsn(_stub_settings()) == STUB_DSN
    assert sentry_dsn(_stub_settings(dsn="   ")) is None
    assert sentry_dsn(Settings(_env_file=None)) is None  # type: ignore[call-arg]


def test_configure_is_noop_without_dsn() -> None:
    """No DSN → not initialised, returns False, stays disabled (the local/CI/E2E path)."""
    assert configure_error_tracking(Settings(_env_file=None)) is False  # type: ignore[call-arg]
    assert is_enabled() is False


def test_bind_request_scope_is_noop_when_disabled() -> None:
    """With Sentry disabled, binding the request scope does nothing and never raises."""
    assert is_enabled() is False
    error_tracking.bind_request_scope(USER_ID)  # must not raise / must not init Sentry


# ── Enabled path: environment + scope binding ───────────────────────────────────────────────────


def test_configure_enables_and_stamps_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")
    transport = MemoryTransport()
    assert configure_error_tracking(_stub_settings(), transport=transport) is True
    assert is_enabled() is True

    sentry_sdk.capture_message("hello")
    sentry_sdk.flush()
    assert transport.events, "expected the in-memory transport to receive an event"
    assert transport.events[-1]["environment"] == "staging"


def test_bind_scope_sets_user_without_active_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a request (no recording span) the user is bound but no trace_id tag is added."""
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "local")
    transport = MemoryTransport()
    configure_error_tracking(_stub_settings(), transport=transport)

    error_tracking.bind_request_scope(USER_ID)
    sentry_sdk.capture_message("no-span")
    sentry_sdk.flush()

    event = transport.events[-1]
    assert event["user"]["id"] == str(USER_ID)
    assert "trace_id" not in event.get("tags", {})


# ── End-to-end: the deliberately-failing debug route ──────────────────────────────────────────────


def test_debug_error_captures_user_and_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    """An authed hit on /__test__/debug-error raises and is captured with user_id + trace_id."""
    monkeypatch.setenv("LLM_PROVIDER", "fake")  # mount the test-only router
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")
    transport = MemoryTransport()
    # Enable Sentry (with the in-memory transport) BEFORE building the app so the Starlette
    # integration is patched in, and stop create_app from re-running configure (which would either
    # disable Sentry or re-init it without our capturing transport).
    assert configure_error_tracking(_stub_settings(), transport=transport) is True
    monkeypatch.setattr("app.main.configure_error_tracking", lambda *a, **k: False)

    app = create_app()
    install_test_auth(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__test__/debug-error", headers=auth_header(USER_ID))

    assert response.status_code == 500
    # The response body must not leak internals (Starlette's generic 500 text).
    assert "Sentry verification" not in response.text

    sentry_sdk.flush()
    error_events = [e for e in transport.events if e.get("level") == "error" or "exception" in e]
    assert error_events, f"expected a captured error event; got {transport.events}"
    event = error_events[-1]
    assert event["user"]["id"] == str(USER_ID)
    trace_id = event["tags"]["trace_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", trace_id), trace_id
    assert event["environment"] == "staging"


def test_debug_error_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anonymous callers cannot reach the debug route (401), so it leaks nothing."""
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    transport = MemoryTransport()
    configure_error_tracking(_stub_settings(), transport=transport)
    monkeypatch.setattr("app.main.configure_error_tracking", lambda *a, **k: False)

    app = create_app()
    install_test_auth(app)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/__test__/debug-error")  # no Authorization header

    assert response.status_code == 401
