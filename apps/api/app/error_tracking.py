"""Sentry error tracking for the FastAPI backend (task 5.4.1).

Sentry is initialised **only** when ``SENTRY_DSN_API`` is set — a no-op with zero network egress
otherwise, mirroring the OTLP-exporter discipline in :mod:`app.observability`. So local dev, CI, and
the FakeLLM E2E never reach Sentry, while a deployed environment that sets the DSN reports its
unhandled exceptions automatically (via the Sentry FastAPI/Starlette integration).

Each captured event is correlated to the rest of the observability stack:

* ``environment`` is stamped from ``DEPLOYMENT_ENVIRONMENT`` (the same tag the tracer/meter carry,
  via :func:`app.observability.deployment_environment`), so Sentry issues filter by environment
  consistently with Tempo/Mimir/Loki;
* every request binds the authenticated ``user.id`` and a ``trace_id`` tag onto Sentry's
  per-request isolation scope (:func:`bind_request_scope`, called from
  :func:`app.deps.get_current_user`). The ``trace_id`` is the **active OpenTelemetry span's** trace
  id, so a Sentry issue carries a ``trace_id`` that resolves to the matching Grafana Tempo trace
  (the cross-tool link the roadmap calls for).

Binding on the isolation scope (rather than reading a contextvar inside Sentry's ``before_send``) is
deliberate: the scope is created once per request at the outermost ASGI layer and shared down, so a
mutation made while the auth dependency runs is visible when the exception is captured higher up the
stack — unlike a contextvar rebinding, which does not propagate back across the
``BaseHTTPMiddleware`` task boundary (the same constraint documented for the access-log ``user_id``
in :mod:`app.request_context`).

The web app uses a **separate**, browser-safe DSN (``VITE_SENTRY_DSN_WEB``) — see
``apps/web/src/lib/error-tracking.ts``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.observability import current_trace_id, deployment_environment

if TYPE_CHECKING:
    from app.settings import Settings

#: Sentry event tag carrying the active OpenTelemetry trace id (32 hex), so an issue links to its
#: Grafana Tempo trace. Named ``trace_id`` to match the log-correlation field (5.3.2).
TRACE_ID_TAG = "trace_id"

# Whether ``sentry_sdk.init`` has run with a real DSN this process. Gates the per-request scope
# binding so it is a cheap no-op (no ``sentry_sdk`` import, no work) when Sentry is disabled — the
# local/CI/E2E path. Set by :func:`configure_error_tracking`.
_enabled = False


def sentry_dsn(settings: Settings) -> str | None:
    """The backend Sentry DSN from ``settings``, or ``None`` when unset/blank (Sentry disabled)."""
    dsn = settings.sentry_dsn_api.strip()
    return dsn or None


def is_enabled() -> bool:
    """Whether Sentry was initialised with a real DSN this process."""
    return _enabled


def configure_error_tracking(settings: Settings, *, transport: Any = None) -> bool:
    """Initialise Sentry iff ``SENTRY_DSN_API`` is set; return whether it initialised.

    Called once from :func:`app.main.create_app`. With no DSN this is a no-op with zero egress (the
    local/CI/E2E path) and returns ``False``. With a DSN it calls ``sentry_sdk.init`` with the
    Starlette + FastAPI integrations (so unhandled request exceptions are captured), stamps
    ``environment`` from :func:`app.observability.deployment_environment`, and disables PII capture
    (``send_default_pii=False``) — the only user data attached is the opaque ``user.id`` bound per
    request. ``transport`` is injected by tests to capture events without network; production passes
    ``None`` so Sentry uses its default HTTP transport.
    """
    global _enabled
    dsn = sentry_dsn(settings)
    if dsn is None:
        _enabled = False
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=deployment_environment(),
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # Never auto-attach request headers/cookies/body or the client IP — the only identifying
        # data on an event is the opaque user id bound in bind_request_scope().
        send_default_pii=False,
        transport=transport,
    )
    _enabled = True
    return True


def bind_request_scope(user_id: uuid.UUID) -> None:
    """Bind the request's ``user.id`` + ``trace_id`` tag onto Sentry's isolation scope (5.4.1).

    A no-op (cheap flag check, no import) unless Sentry is enabled. When enabled it stamps the
    per-request isolation scope so any exception captured later in the request carries:

    * ``user.id`` — the authenticated user's UUID (the opaque id only; no email/PII); and
    * a ``trace_id`` tag — the active OpenTelemetry span's trace id, so the Sentry issue links to
      the matching Grafana Tempo trace. Omitted when no recording span is active.

    Called from :func:`app.deps.get_current_user` once the identity is verified — additive, it never
    changes which tokens are accepted.
    """
    if not _enabled:
        return
    import sentry_sdk

    scope = sentry_sdk.get_isolation_scope()
    scope.set_user({"id": str(user_id)})
    trace_id = current_trace_id()
    if trace_id is not None:
        scope.set_tag(TRACE_ID_TAG, trace_id)


def _reset_for_tests() -> None:
    """Disable Sentry + clear the enabled flag (tests only), so init never leaks across tests."""
    global _enabled
    import sentry_sdk

    sentry_sdk.init(dsn="")  # an empty DSN yields a disabled client (no capture, no transport)
    _enabled = False
