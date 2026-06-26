"""Task 3.5.1 — the global concurrency cap bounds in-flight provider calls.

The headline verify, :func:`test_semaphore_caps_inflight`, fires more concurrent calls than the cap
through a slow fake provider that records its own concurrent-in-flight high-water-mark thread-safely
(the calls run in real worker threads via ``asyncio.to_thread``, so they genuinely overlap) and
asserts the semaphore never lets more than the cap run at once. The rest cover the bounded-wait →
:class:`ProviderBusy` busy path, the singleton dependency, value/exception propagation, and that the
busy/transient errors render the friendly **503 ``server_busy``** contract at the HTTP layer.

These are pure asyncio/ASGI tests — no DB and no real LLM: the provider calls are a local slow
stand-in and the HTTP checks drive an in-memory ASGI app.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.llm_runner import (
    BUSY_RETRY_AFTER_SECONDS,
    SERVER_BUSY_MESSAGE,
    LLMConcurrencyLimiter,
    ProviderBusy,
    get_llm_limiter,
    register_llm_handlers,
    reset_llm_limiter,
)
from lengua_core.llm.retry import LLMTransientError

pytestmark = pytest.mark.asyncio


class _SlowProvider:
    """A slow, blocking stand-in that records the high-water-mark of concurrent in-flight calls.

    Increments a shared in-flight counter under a :class:`threading.Lock` (the calls run in worker
    threads, so the counter must be thread-safe), holds for ``hold`` seconds with a real
    :func:`time.sleep` so overlapping calls genuinely coexist, then decrements.
    """

    def __init__(self, hold: float = 0.05) -> None:
        self._hold = hold
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0
        self.calls = 0

    def __call__(self) -> int:
        with self._lock:
            self._in_flight += 1
            self.calls += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(self._hold)
            return self.calls
        finally:
            with self._lock:
                self._in_flight -= 1


async def test_semaphore_caps_inflight() -> None:
    limiter = LLMConcurrencyLimiter(max_concurrency=2)
    provider = _SlowProvider(hold=0.05)

    # Fire six concurrent runs; with a cap of two, at most two threads may be in flight at once.
    await asyncio.gather(*(limiter.run(provider) for _ in range(6)))

    assert provider.calls == 6  # every call ran (none dropped)
    assert provider.max_in_flight == 2  # the cap held — and two ran truly in parallel


async def test_busy_when_no_slot_frees_within_timeout() -> None:
    limiter = LLMConcurrencyLimiter(max_concurrency=1, acquire_timeout=0.05)
    started = threading.Event()
    release = threading.Event()

    def _hold() -> int:
        started.set()
        release.wait(timeout=2.0)
        return 1

    # Occupy the single slot, then attempt a second call that can't get a permit within the timeout.
    holder = asyncio.create_task(limiter.run(_hold))
    await asyncio.to_thread(started.wait, 1.0)
    try:
        with pytest.raises(ProviderBusy):
            await limiter.run(lambda: 2)
    finally:
        release.set()
    assert await holder == 1


async def test_run_returns_value_and_propagates_exception() -> None:
    limiter = LLMConcurrencyLimiter(max_concurrency=2)
    assert await limiter.run(lambda: 7) == 7

    def _boom() -> int:
        raise LLMTransientError(RuntimeError("persistent upstream 503"))

    # A persistent-transient error from the provider call propagates unchanged (the app maps it).
    with pytest.raises(LLMTransientError):
        await limiter.run(_boom)


async def test_get_llm_limiter_is_singleton_and_resettable() -> None:
    reset_llm_limiter()
    first = get_llm_limiter()
    assert get_llm_limiter() is first  # shared process-wide singleton
    reset_llm_limiter()
    assert get_llm_limiter() is not first  # rebuilt from settings after a reset


async def test_busy_and_transient_render_503_server_busy() -> None:
    app = FastAPI()
    register_llm_handlers(app)

    @app.get("/_busy")
    async def _busy() -> None:
        raise ProviderBusy()

    @app.get("/_transient")
    async def _transient() -> None:
        raise LLMTransientError(RuntimeError("persistent 429"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ("/_busy", "/_transient"):
            resp = await client.get(path)
            assert resp.status_code == 503
            assert resp.json() == {"code": "server_busy", "message": SERVER_BUSY_MESSAGE}
            assert resp.headers["Retry-After"] == str(BUSY_RETRY_AFTER_SECONDS)
