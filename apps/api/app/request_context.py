"""Per-request context: the authenticated user id, for log correlation (task 5.3.2).

A single :class:`contextvars.ContextVar` carrying the current request's user id. It is set where
the identity resolves (:func:`app.deps.get_current_user`, the canonical auth dependency every
authenticated route funnels through) and read by the logging correlation filter
(:class:`app.observability.TraceCorrelationFilter`) so every log record emitted *inside* a request
carries ``user_id`` alongside the active span's ``trace_id`` / ``span_id``.

Why a contextvar (not request state): it needs no plumbing through services/repositories — a log
emitted deep in the call stack reads the current value directly. It is **task-local**: each request
runs in its own asyncio task whose context is copied at creation, so a value set during one request
is invisible to other requests and to the process root (it defaults to ``None`` outside a request).
For that reason it is set without an explicit reset — there is no cross-request bleed to undo, and
keeping :func:`get_current_user` a plain (non-generator) dependency leaves the auth contract
unchanged (task 5.3.2 adds correlation **without** changing auth logic).

Note on the access log: the one-line-per-request access log is emitted by
:class:`app.observability.RequestLoggingMiddleware`, which runs in the *outer* ASGI context (the
``BaseHTTPMiddleware`` task), where this contextvar — set by the auth dependency in the *inner*
request task — is not visible, so the access line's ``user_id`` is ``None``. In-request application
logs (endpoints/services, the inner task) carry the real ``user_id``.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

#: The authenticated user's id for the current request context (``None`` outside a request).
_current_user_id: ContextVar[uuid.UUID | None] = ContextVar("lengua_current_user_id", default=None)


def set_current_user_id(user_id: uuid.UUID | None) -> None:
    """Record the authenticated user's id on the current context (called once per request)."""
    _current_user_id.set(user_id)


def get_current_user_id() -> uuid.UUID | None:
    """The authenticated user's id for the current context, or ``None`` outside a request."""
    return _current_user_id.get()
