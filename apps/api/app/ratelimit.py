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
    (when under the limit) or rejects it. When a user's window empties (all timestamps aged out, or
    a disabled limiter that never records any), its dict entry is reclaimed so the map stays bounded
    rather than growing one slot per distinct user id ever seen. The clock is injectable so tests
    advance time without sleeping; the default is :func:`time.monotonic` (immune to clock jumps).
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

        if not hits:
            # Every timestamp aged out (or a disabled limiter with limit 0 never records any): drop
            # the now-empty deque so the map can't grow by one permanent slot per distinct user id
            # ever seen. A later hit simply re-creates the entry via the defaultdict. Bounds memory,
            # mirroring the size-capped app.discover_cache.
            del self._hits[user_id]

        if len(hits) >= self._limit:
            # Seconds until the oldest in-window hit ages out (== a slot frees). When the limit is 0
            # the window can never have room, so wait a whole window. Floor of 1s so the client
            # always backs off a beat.
            free_in = (hits[0] + self._window - now) if hits else self._window
            retry_after = max(math.ceil(free_in), 1)
            return RateLimitDecision(
                allowed=False, count=len(hits), limit=self._limit, retry_after=retry_after
            )

        hits = self._hits[user_id]  # re-create the entry if it was just reclaimed, then record.
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


# ── Public account-deletion-request limiter (Phase 8, task 8.3.1) ──────────────────────────────
# The unauthenticated /delete-account form emails a confirmation link. Without a per-address cap the
# form could be used to *bomb a victim's inbox* with deletion emails, so we allow only a few
# requests per email per hour. Keyed by a uuid5 of the normalized email (the limiter key is a UUID),
# with a 1-hour window — distinct from the per-minute per-user LLM limiter above.
DELETION_REQUEST_LIMIT = 5
DELETION_REQUEST_WINDOW_SECONDS = 3600.0


@lru_cache(maxsize=1)
def _public_deletion_rate_limiter() -> InProcessRateLimiter:
    """Process-wide singleton limiter for the public deletion-request endpoint."""
    return InProcessRateLimiter(
        limit=DELETION_REQUEST_LIMIT, window_seconds=DELETION_REQUEST_WINDOW_SECONDS
    )


def get_public_deletion_rate_limiter() -> RateLimiter:
    """FastAPI dependency: the shared limiter guarding ``POST /account/deletion-request``."""
    return _public_deletion_rate_limiter()


# ── Per-IP cap on the same endpoint (round-3 DoS hardening) ────────────────────────────────────
# The per-address limiter above stops using the form to inbox-bomb ONE victim, but an attacker
# rotating through DISTINCT emails slips past it (each email is a fresh key). A coarser per-source
# (per-IP) cap bounds that distinct-email flood. Sized higher than the per-email cap — a shared
# NAT / office IP may host a handful of legitimate users — but low enough to blunt a flood. Same
# 1-hour window as the per-email cap.
DELETION_REQUEST_IP_LIMIT = 30


@lru_cache(maxsize=1)
def _public_deletion_ip_rate_limiter() -> InProcessRateLimiter:
    """Process-wide singleton per-IP limiter for the public deletion-request endpoint."""
    return InProcessRateLimiter(
        limit=DELETION_REQUEST_IP_LIMIT, window_seconds=DELETION_REQUEST_WINDOW_SECONDS
    )


def get_public_deletion_ip_rate_limiter() -> RateLimiter:
    """FastAPI dependency: the shared per-IP limiter guarding ``POST /account/deletion-request``."""
    return _public_deletion_ip_rate_limiter()
