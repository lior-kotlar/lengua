"""The single async chokepoint every LLM provider call goes through (task 3.5.1).

The provider methods behind the ``lengua_core.llm`` seam are **synchronous/blocking** (they make a
network round-trip). Calling one directly from an async route would (a) block the event loop for the
whole request and (b) place no bound on how many provider calls run at once. This module fixes both:

* :class:`LLMConcurrencyLimiter.run` offloads each blocking provider call to a worker thread
  (``asyncio.to_thread``) **under a process-global semaphore** sized by
  :data:`~app.settings.Settings.llm_max_concurrency` (``LLM_MAX_CONCURRENCY``, default 4). The
  semaphore bounds in-flight provider calls; the thread keeps the event loop responsive so other
  requests still progress (and so concurrent calls are *genuinely* concurrent, not serialised).
* Over the cap a request **waits briefly** (bounded by :data:`ACQUIRE_TIMEOUT_SECONDS`) for a slot;
  if none frees it raises :class:`ProviderBusy` — never an unbounded queue, never a 500. The app
  maps it to **503** ``{"code": "server_busy", ...}`` with a short ``Retry-After``.

The same 503 ``server_busy`` response also renders :class:`~lengua_core.llm.LLMTransientError` — a
provider 429/5xx that *persisted* across every retry (task 3.5.2) — so "the LLM backend is
temporarily unavailable" is one friendly contract whether the cause is local saturation or upstream
rate-limiting.

The limiter is exposed as the process-wide singleton :func:`get_llm_limiter` (a FastAPI dependency,
mirroring ``app.ratelimit.get_rate_limiter``) so call sites get one shared semaphore and tests
override it (or :func:`reset_llm_limiter` rebuilds a fresh one sized from current settings).

**Why this matters for the cost guard.** The global kill-switch (``app.quota``) reads the budget
*before* the provider call and increments *after* success, so concurrent in-flight requests can
overshoot the ceiling. :data:`~app.settings.Settings.llm_max_concurrency` is the hard bound on that
overshoot. Together with the (Phase-6) distributed rate limiter it is what makes scaling beyond one
instance safe.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from functools import lru_cache
from typing import ParamSpec, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import Span

from app.llm_observability import (
    ATTR_LLM_INPUT_SIZE,
    ATTR_LLM_LATENCY_MS,
    ATTR_LLM_MODEL,
    ATTR_LLM_PROVIDER,
    ATTR_LLM_RETRY_COUNT,
    ATTR_LLM_TOKENS_IN,
    ATTR_LLM_TOKENS_OUT,
    record_tokens,
)
from app.prompt_store import warm_prompt_store
from app.settings import get_settings
from lengua_core.llm import LLMProvider, LLMTransientError
from lengua_core.llm.usage import capture_usage

P = ParamSpec("P")
R = TypeVar("R")

#: How long a request waits for a free concurrency slot before giving up with :class:`ProviderBusy`.
#: Short and bounded — we never queue unboundedly; a saturated server fails fast and friendly.
ACQUIRE_TIMEOUT_SECONDS = 5.0

#: ``Retry-After`` hint (seconds) returned with the busy 503 — a brief, client-friendly backoff.
BUSY_RETRY_AFTER_SECONDS = 1

#: The friendly, user-facing message for the busy 503 (part of the API contract; shared with tests).
SERVER_BUSY_MESSAGE = "The server is busy, please try again in a moment."


class ProviderBusy(Exception):
    """Raised when no concurrency slot frees within the bounded wait — rendered **503 server_busy**.

    The load-shedding signal: too many provider calls are already in flight (the global semaphore is
    full) and one did not free within :data:`ACQUIRE_TIMEOUT_SECONDS`. A bare ``Exception`` so the
    app-level handler renders it identically wherever it surfaces (route dependency or service).
    """


class LLMConcurrencyLimiter:
    """Bounds concurrent in-flight provider calls with a global asyncio semaphore.

    Each :meth:`run` offloads the blocking provider call to a thread (so the event loop is never
    stalled) and holds one semaphore permit for its duration, so at most ``max_concurrency``
    provider calls run at once. Over the limit a caller waits up to ``acquire_timeout`` for a
    permit, then raises :class:`ProviderBusy` rather than queuing without bound.
    """

    def __init__(
        self,
        *,
        max_concurrency: int,
        acquire_timeout: float = ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._acquire_timeout = acquire_timeout
        self.max_concurrency = max_concurrency

    async def run(self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """Acquire a slot, run the blocking ``fn(*args, **kwargs)`` in a thread, release the slot.

        Raises :class:`ProviderBusy` if no slot frees within ``acquire_timeout``. Any exception from
        ``fn`` (including :class:`~lengua_core.llm.LLMTransientError` from the retry helper)
        propagates unchanged; the permit is always released in ``finally``.
        """
        try:
            async with asyncio.timeout(self._acquire_timeout):
                await self._semaphore.acquire()
        except TimeoutError as exc:
            raise ProviderBusy() from exc
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        finally:
            self._semaphore.release()


def _provider_identity(provider: LLMProvider) -> tuple[str, str]:
    """``(provider_name, model)`` for the ``llm.provider`` / ``llm.model`` span attributes.

    Reads the optional ``name`` / ``model`` attributes the concrete providers expose (Groq / Gemini
    / FakeLLM), falling back to the class name so any structural provider still yields a value.
    """
    name = str(getattr(provider, "name", type(provider).__name__))
    model = str(getattr(provider, "model", name))
    return name, model


async def run_provider[R](
    limiter: LLMConcurrencyLimiter,
    provider: LLMProvider,
    span: Span | None,
    call: Callable[[], R],
    *,
    input_size: int | None = None,
    kind: str | None = None,
) -> R:
    """Run the provider ``call`` under the concurrency cap, instrumented (tasks 3.8.1/5.2.1/5.2.4).

    ``call`` is the blocking provider invocation pre-bound to its arguments (a zero-arg callable,
    e.g. ``lambda: provider.generate_cards(words, language, …)``). Wrapping it here keeps this the
    single place each provider call passes through. When a ``span`` is supplied (the per-call
    ``llm.call`` span the cost guard started) it stamps the ``llm.*`` attributes: ``llm.provider`` /
    ``llm.model`` and ``llm.input_size`` (the per-kind request size) up front, ``llm.latency_ms``
    always (even when the call raises), and ``llm.tokens_in`` / ``llm.tokens_out`` / ``retry_count``
    from the telemetry the provider + retry helper reported (via
    :func:`lengua_core.llm.usage.capture_usage`).

    On a successful call, when ``kind`` is supplied it also adds the consumed tokens to
    ``llm_tokens_total{kind, direction}`` (task 5.2.4) — counted here at the provider boundary
    because that is where the tokens were actually spent. With no span (a provider call outside a
    gated request, e.g. a service unit test) it is a thin pass-through to the limiter. Any exception
    from ``call`` propagates unchanged.

    Before dispatching the (blocking, threaded) provider call, it refreshes the DB-backed prompt
    snapshot on the event loop (GitHub #80): ``prompts.system_instruction`` /
    ``suggestion_instruction`` run **inside** ``call`` on a worker thread and can't ``await``, so
    the active ``prompt_versions`` set must be materialised first. The warm is best-effort and fails
    safe to the code defaults, so it never blocks or breaks a generation.
    """
    # Materialise the active prompt set for the synchronous builders (see the docstring). Cheap
    # after the first call (TTL-cached); a no-op fast path when no store installed / on any error.
    await warm_prompt_store()
    if span is not None:
        name, model = _provider_identity(provider)
        span.set_attribute(ATTR_LLM_PROVIDER, name)
        span.set_attribute(ATTR_LLM_MODEL, model)
        if input_size is not None:
            span.set_attribute(ATTR_LLM_INPUT_SIZE, input_size)
    start = time.perf_counter()
    with capture_usage() as usage:
        try:
            result = await limiter.run(call)
        finally:
            if span is not None:
                latency_ms = round((time.perf_counter() - start) * 1000, 3)
                span.set_attribute(ATTR_LLM_LATENCY_MS, latency_ms)
    if span is not None:
        span.set_attribute(ATTR_LLM_TOKENS_IN, usage.tokens_in)
        span.set_attribute(ATTR_LLM_TOKENS_OUT, usage.tokens_out)
        span.set_attribute(ATTR_LLM_RETRY_COUNT, usage.retry_count)
    # Reached only on success (an exception propagates out of the ``with`` above): the tokens were
    # genuinely consumed, so count them against the budget-side metric.
    if kind is not None:
        record_tokens(kind, usage.tokens_in, usage.tokens_out)
    return result


@lru_cache(maxsize=1)
def _default_llm_limiter() -> LLMConcurrencyLimiter:
    """The process-wide singleton limiter, sized from settings (cached, so the semaphore is one)."""
    return LLMConcurrencyLimiter(max_concurrency=get_settings().llm_max_concurrency)


def get_llm_limiter() -> LLMConcurrencyLimiter:
    """FastAPI dependency: the process-wide :class:`LLMConcurrencyLimiter`.

    Returns the shared singleton so every provider call counts against one semaphore (a fresh
    limiter per request would impose no real bound). Tests override this dependency with their own
    limiter (see ``tests/api/conftest.py``), or call :func:`reset_llm_limiter` to rebuild it.
    """
    return _default_llm_limiter()


def reset_llm_limiter() -> None:
    """Drop the cached singleton so the next :func:`get_llm_limiter` rebuilds it from settings."""
    _default_llm_limiter.cache_clear()


async def _server_busy_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`ProviderBusy` / :class:`LLMTransientError` as the friendly busy **503**.

    One response for both causes — local saturation (the concurrency cap) and a persistent upstream
    429/5xx — because to a client both mean "temporarily unavailable, retry shortly". Carries a
    short ``Retry-After`` so a well-behaved client backs off.
    """
    return JSONResponse(
        status_code=503,
        content={"code": "server_busy", "message": SERVER_BUSY_MESSAGE},
        headers={"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)},
    )


def register_llm_handlers(app: FastAPI) -> None:
    """Wire the busy/transient → 503 ``server_busy`` handlers onto ``app`` (from ``create_app``)."""
    app.add_exception_handler(ProviderBusy, _server_busy_handler)
    app.add_exception_handler(LLMTransientError, _server_busy_handler)
