"""Per-user sliding-window rate limiting (Phase 3.3).

The daily caps in :mod:`app.quota` are per-day ceilings; this limiter smooths *bursts* — at most
:data:`Settings.rate_limit_per_min` gated LLM requests per user per rolling minute, across all
``kind``s — so one client can't hammer the provider's requests-per-minute ceiling. It runs *before*
the daily-cap gate (see the gate order in :mod:`app.quota`).

**Decision (locked): in-process, no new dependency.** This is a process-local *sliding-window log*
(``slowapi`` was rejected — heavier, and its clock is awkward to fake). The implementation takes an
**injectable clock** so tests fake time deterministically instead of sleeping.

.. warning::

    **Single-instance only — distributed swap deferred to Phase 6.** The window lives in this
    process's memory, so if Cloud Run scales to >1 instance the per-user count is *under-counted*
    (each replica keeps its own window). When the service runs multi-instance, replace
    :class:`InProcessRateLimiter` with a shared backend (Postgres atomic counter or Upstash Redis
    sliding window) behind this same :class:`RateLimiter` Protocol — the call sites (the
    :class:`~app.quota.QuotaGuard` chain) do not change. The seam is the Protocol + the
    :func:`get_rate_limiter` dependency.
"""

from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.settings import get_settings

#: One rolling window is a minute; the per-user *count* within it is the limit.
WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class RateLimitDecision:
    """The outcome of one rate-limit check.

    ``allowed`` says whether the request may proceed; when it is rejected, ``retry_after`` is the
    whole number of seconds until the window frees a slot (always ``>= 1``) — surfaced to the client
    as the HTTP ``Retry-After`` header. ``count`` is the number of hits now counted in the user's
    window (including this one when allowed) and ``limit`` the configured ceiling — both are useful
    for tests/diagnostics.
    """

    allowed: bool
    count: int
    limit: int
    retry_after: int


class RateLimiter(Protocol):
    """A per-user rate limiter. The single seam a distributed backend would implement (Phase 6)."""

    def hit(self, user_id: uuid.UUID) -> RateLimitDecision:
        """Record (or reject) one request for ``user_id`` and return the decision."""
        ...


class InProcessRateLimiter:
    """A sliding-window-log rate limiter held entirely in this process's memory.

    Per user it keeps the monotonic timestamps of the requests inside the current window; each
    :meth:`hit` first evicts timestamps older than the window, then either records the new request
    (when under the limit) or rejects it. The clock is injectable so tests advance time without
    sleeping; the default is :func:`time.monotonic` (immune to wall-clock jumps).
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = float(window_seconds)
        self._clock = clock
        self._hits: dict[uuid.UUID, deque[float]] = defaultdict(deque)

    def hit(self, user_id: uuid.UUID) -> RateLimitDecision:
        """Count one request for ``user_id`` against the rolling window.

        Evicts expired timestamps, then: if the window is full, reject with a ``retry_after`` of the
        seconds until the oldest timestamp ages out (so a slot frees); otherwise record ``now`` and
        allow. A rejected request is **not** recorded — only allowed requests consume a slot.
        """
        now = self._clock()
        hits = self._hits[user_id]
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            # Seconds until the oldest in-window hit ages out (== a slot frees). When the limit is 0
            # the window can never have room, so wait a whole window. Floor of 1s so the client
            # always backs off a beat.
            free_in = (hits[0] + self._window - now) if hits else self._window
            retry_after = max(math.ceil(free_in), 1)
            return RateLimitDecision(
                allowed=False, count=len(hits), limit=self._limit, retry_after=retry_after
            )

        hits.append(now)
        return RateLimitDecision(allowed=True, count=len(hits), limit=self._limit, retry_after=0)


@lru_cache(maxsize=1)
def _default_rate_limiter() -> InProcessRateLimiter:
    """The process-wide singleton limiter, sized from settings (cached so it survives requests)."""
    return InProcessRateLimiter(
        limit=get_settings().rate_limit_per_min, window_seconds=WINDOW_SECONDS
    )


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency: the process-wide :class:`RateLimiter`.

    Returns the shared singleton so its window survives across requests (a fresh limiter per request
    would never count more than one). Tests override this dependency with a fresh limiter + a fake
    clock so the global window can't bleed between tests (see ``tests/quota``).
    """
    return _default_rate_limiter()
