"""LLM per-call telemetry reporting seam (tasks 3.8.1 / 5.2.1).

The observability layer wants per-call attributes on every ``llm.call`` span — ``llm.tokens_in`` /
``llm.tokens_out`` (3.8.1) and ``llm.retry_count`` (5.2.1) — but the provider methods behind
:class:`~lengua_core.llm.base.LLMProvider` return *parsed* results (cards / words / a note), not the
vendor's token usage or the number of backoff retries. Rather than change every method's return
type, the provider (and the shared :func:`~lengua_core.llm.retry.call_with_retry` helper) **report**
that telemetry through this tiny side-channel and the app **captures** it at the call boundary
(:func:`app.llm_runner.run_provider`).

The seam is a single :class:`contextvars.ContextVar` holding a *mutable* :class:`TokenUsage`:

* the boundary opens :func:`capture_usage` (which sets a fresh :class:`TokenUsage` into the var) and
  reads it back after the call;
* the provider — even when its blocking call is offloaded to a worker thread via
  ``asyncio.to_thread`` — calls :func:`report_usage` / :func:`report_retry_count`, which *mutate the
  same object*. This works across the thread hop because ``asyncio.to_thread`` copies the context
  (so the var still points at the boundary's :class:`TokenUsage` instance) and the provider mutates
  that shared object in place; the boundary then sees the populated values once the thread joins.

When no capture scope is active (a provider called directly in a unit test, the deterministic
``FakeLLM`` outside the boundary, or the legacy Streamlit path) :func:`report_usage` /
:func:`report_retry_count` are no-ops, so reporting is always safe and never required.

:func:`report_groq_usage` / :func:`report_gemini_usage` adapt each vendor's response shape (read
purely by ``getattr`` — no vendor imports here) to :func:`report_usage`.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    """Per-call provider telemetry the call boundary reads back (defaults until a provider reports).

    Carries the prompt/completion token counts (``tokens_in`` / ``tokens_out``, task 3.8.1) and the
    number of backoff retries the call took before succeeding (``retry_count``, task 5.2.1 — ``0``
    means the first attempt succeeded). Both are reported through this seam rather than threaded
    through every provider method's return type.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    retry_count: int = 0


#: The active capture sink, or ``None`` outside a :func:`capture_usage` scope. Holds a *mutable*
#: :class:`TokenUsage` so a provider running in a ``to_thread`` worker can populate it in place.
_sink: contextvars.ContextVar[TokenUsage | None] = contextvars.ContextVar(
    "llm_token_usage_sink", default=None
)


@contextmanager
def capture_usage() -> Iterator[TokenUsage]:
    """Open a usage-capture scope: yields a :class:`TokenUsage` a nested provider call fills in.

    Set the fresh sink *before* dispatching the provider call (so an ``asyncio.to_thread`` copy of
    the context still points at this object), then read the populated values after the call returns.
    The previous sink is restored on exit so nested scopes don't leak.
    """
    usage = TokenUsage()
    token = _sink.set(usage)
    try:
        yield usage
    finally:
        _sink.reset(token)


def report_usage(tokens_in: int, tokens_out: int) -> None:
    """Record this call's token usage into the active :func:`capture_usage` sink (else a no-op)."""
    sink = _sink.get()
    if sink is not None:
        sink.tokens_in = int(tokens_in)
        sink.tokens_out = int(tokens_out)


def report_retry_count(retry_count: int) -> None:
    """Record this call's retry count into the active :func:`capture_usage` sink (else a no-op).

    Called by :func:`~lengua_core.llm.retry.call_with_retry` once the outcome is known, so the
    per-call ``llm.call`` span can carry ``llm.retry_count`` (task 5.2.1). ``0`` means the first
    attempt succeeded; ``n`` means ``n`` transient failures were retried first.
    """
    sink = _sink.get()
    if sink is not None:
        sink.retry_count = int(retry_count)


def _coerce_token_count(value: Any) -> int:
    """A non-negative int from a vendor token field; 0 when it's missing/None/non-numeric."""
    return value if isinstance(value, int) and value >= 0 else 0


def report_groq_usage(response: Any) -> None:
    """Report token usage from a Groq chat-completion response (``response.usage``)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    report_usage(
        _coerce_token_count(getattr(usage, "prompt_tokens", None)),
        _coerce_token_count(getattr(usage, "completion_tokens", None)),
    )


def report_gemini_usage(response: Any) -> None:
    """Report token usage from a Gemini response (``response.usage_metadata``)."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return
    report_usage(
        _coerce_token_count(getattr(meta, "prompt_token_count", None)),
        _coerce_token_count(getattr(meta, "candidates_token_count", None)),
    )
