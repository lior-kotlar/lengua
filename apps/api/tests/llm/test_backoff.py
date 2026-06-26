"""Task 3.5.2 — exponential backoff + jitter; a persistent 429/5xx ends in a friendly busy error.

Two halves:

* :func:`test_retries_then_gives_up` (the verify) drives a fake provider that returns HTTP 429 on
  every attempt: the retries back off (faked clock + faked jitter, so no real sleeping) and then the
  helper raises the clean, typed :class:`LLMTransientError` — never the raw vendor exception leaking
  out as an unhandled 500.
* :func:`test_persistent_transient_renders_503_server_busy` proves that typed error reaches the HTTP
  layer as the friendly **503 ``server_busy``** the concurrency cap shares (the app registers the
  same handler for it), so a persistent upstream rate-limit is a graceful response, not a crash.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.llm_runner import (
    BUSY_RETRY_AFTER_SECONDS,
    SERVER_BUSY_MESSAGE,
    register_llm_handlers,
)
from lengua_core.llm.retry import LLMTransientError, call_with_retry


class _RateLimited(Exception):
    """A stand-in for a provider HTTP 429 (e.g. ``groq.RateLimitError``)."""

    def __init__(self, status_code: int = 429) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


@pytest.mark.disable_socket
def test_retries_then_gives_up() -> None:
    sleeps: list[float] = []
    attempts = 0

    def always_429() -> str:
        nonlocal attempts
        attempts += 1
        raise _RateLimited(429)

    with pytest.raises(LLMTransientError) as exc_info:
        call_with_retry(
            always_429,
            is_transient=lambda exc: isinstance(exc, _RateLimited),
            sleep=sleeps.append,
            rng=lambda: 1.0,  # pin jitter to its max → exact, un-jittered backoff
        )

    assert attempts == 3  # max_attempts: the initial call + two retries, all 429
    assert sleeps == [1.0, 2.0]  # two backoff waits before retries 2 and 3 (faked clock)
    # The persistent provider error surfaces as a clean typed error, not the raw vendor exception.
    original = exc_info.value.original
    assert isinstance(original, _RateLimited)
    assert original.status_code == 429
    assert isinstance(exc_info.value.__cause__, _RateLimited)


@pytest.mark.asyncio
async def test_persistent_transient_renders_503_server_busy() -> None:
    app = FastAPI()
    register_llm_handlers(app)

    @app.get("/_persistent_429")
    async def _persistent_429() -> None:
        # What a provider call raises after exhausting its retries on a sticky 429.
        raise LLMTransientError(_RateLimited(429))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/_persistent_429")

    assert resp.status_code == 503
    assert resp.json() == {"code": "server_busy", "message": SERVER_BUSY_MESSAGE}
    assert resp.headers["Retry-After"] == str(BUSY_RETRY_AFTER_SECONDS)
