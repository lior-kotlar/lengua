"""Tasks 3.3.1 / 3.3.2 — per-user sliding-window rate limiting.

* :func:`test_window_counts` exercises :class:`~app.ratelimit.InProcessRateLimiter` directly with a
  faked clock: within one window the per-user counter increments, and once the window elapses it
  resets. No DB / HTTP — it proves the limiter's core sliding-window behaviour in isolation.
* :func:`test_blocks_over_limit` drives the gate end-to-end over HTTP: the ``(limit+1)``th gated
  call within the window returns **429** ``{"code": "rate_limited"}`` with a ``Retry-After`` header,
  and a later call after the window has elapsed is allowed again. The fake clock makes the window
  deterministic (no sleeping).
* :func:`test_default_rate_limiter_is_singleton` covers the process-wide singleton dependency.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.ratelimit import InProcessRateLimiter, get_rate_limiter
from tests.auth_helpers import authenticate_as
from tests.quota.conftest import FakeClock, client_for


def test_window_counts() -> None:
    """Within one window the per-user counter climbs; after the window elapses it resets."""
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=100, window_seconds=60.0, clock=clock)
    user = uuid.uuid4()

    # Each hit within the window increments the count.
    assert limiter.hit(user).count == 1
    assert limiter.hit(user).count == 2
    assert limiter.hit(user).count == 3

    # Part-way through the window the earlier hits are still in range → it keeps climbing.
    clock.advance(30)
    assert limiter.hit(user).count == 4

    # Once the whole window has passed the earliest hits, the count resets to a single fresh hit.
    clock.advance(61)
    assert limiter.hit(user).count == 1

    # The window is per-user — a different id keeps its own independent count.
    assert limiter.hit(uuid.uuid4()).count == 1


def test_default_rate_limiter_is_singleton() -> None:
    """The dependency returns one process-wide limiter (so its window survives across requests)."""
    first = get_rate_limiter()
    second = get_rate_limiter()
    assert first is second
    assert isinstance(first, InProcessRateLimiter)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_blocks_over_limit(quota_app: FastAPI, db_session: AsyncSession) -> None:
    limit = 3
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=limit, window_seconds=60.0, clock=clock)
    quota_app.dependency_overrides[get_rate_limiter] = lambda: limiter
    authenticate_as(quota_app, DEV_USER_ID, email_verified=True)

    # This test is purely about the rate gate, so make the account "established" (created long ago)
    # to keep the day-0 generate clamp out of the way — the daily cap stays the generous default.
    await db_session.execute(
        text("UPDATE profiles SET created_at = now() - interval '30 days' WHERE id = :id"),
        {"id": DEV_USER_ID},
    )

    async with client_for(quota_app) as client:
        lang = await client.post("/languages", json={"name": "Spanish", "code": "es"})
        assert lang.status_code == 200
        gen_body = {"language_id": int(lang.json()["id"]), "words": ["hola"]}

        # The first ``limit`` calls within the window pass the rate gate.
        for _ in range(limit):
            ok = await client.post("/generate", json=gen_body)
            assert ok.status_code == 200, ok.text

        # The (limit+1)th call within the same window is rate-limited: 429 + Retry-After.
        blocked = await client.post("/generate", json=gen_body)
        assert blocked.status_code == 429
        assert blocked.json() == {"code": "rate_limited"}
        assert int(blocked.headers["Retry-After"]) >= 1

        # Advancing past the window frees the slots → a later call is allowed again.
        clock.advance(61)
        allowed = await client.post("/generate", json=gen_body)
        assert allowed.status_code == 200, allowed.text
