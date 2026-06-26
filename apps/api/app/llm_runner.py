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
from collections.abc import Callable
from functools import lru_cache
from typing import ParamSpec, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.settings import get_settings
from lengua_core.llm import LLMTransientError

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
