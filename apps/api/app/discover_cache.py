"""Short-window reuse cache for ``/discover`` previews (Phase 3.6.3).

The cheapest LLM call is the one you never make. A learner who taps "Discover" twice in a row for
the same language + topic does not need a second (billed) provider round-trip — the first preview is
still perfectly good. This module memoises a discover preview for a brief window so an identical
repeat is served from memory: **no provider call, and no daily-cap/global-budget count** (it never
spent the operator key, so it must not be metered — mirroring how an ``/explain`` cache hit is
free).

The cache is keyed by :class:`DiscoverKey` — ``(user_id, language_id, topic, count)`` — so it never
crosses users, languages, topics, or requested sizes. Entries expire after
:data:`~app.settings.Settings.discover_reuse_window_seconds` (``DISCOVER_REUSE_WINDOW_SECONDS``,
default 300). The clock is **injectable** (default :func:`time.monotonic`) so tests advance time
without sleeping, exactly like :mod:`app.ratelimit`.

**Decision (locked): in-process, no new dependency** — mirrors the in-process rate limiter
(:mod:`app.ratelimit`). The store is bounded (expired entries are evicted on every access and the
total is capped at :data:`MAX_ENTRIES`, evicting the oldest) so it cannot leak memory.

.. warning::

    **Single-instance only — distributed swap deferred to Phase 6.** The cache lives in this
    process's memory, so if Cloud Run scales to >1 instance a repeat that lands on a *different*
    replica simply misses (it makes a fresh, fully-gated provider call — never wrong, just not
    reused). When the service runs multi-instance, back this same :class:`DiscoverCache` Protocol
    with a shared store (Redis/Upstash or a Postgres table with a TTL) — the call site
    (:meth:`app.services.discover.DiscoverService.suggest`) does not change. The seam is the
    Protocol + the :func:`get_discover_cache` dependency (the same caveat family as the in-process
    rate limiter).
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.settings import get_settings

#: Hard cap on the number of cached previews held at once. Each entry is a handful of short strings,
#: so this is tiny; it exists purely so a long-running process can't grow the cache without bound.
#: When exceeded, the oldest-stored entry is evicted (FIFO) — alongside the TTL eviction.
MAX_ENTRIES = 1024


@dataclass(frozen=True)
class DiscoverKey:
    """The cache key for one discover preview — its full scope.

    Includes ``user_id`` (never reuse one learner's preview for another), ``language_id``, the
    optional ``topic`` (``None`` and ``""`` are distinct keys, matching the request as sent), and
    the requested ``count`` (a 5-word preview must not satisfy a later 10-word request). Frozen so
    it is hashable and usable as a dict key.
    """

    user_id: uuid.UUID
    language_id: int
    topic: str | None
    count: int


class DiscoverCache(Protocol):
    """A short-window discover-preview cache. The seam a distributed backend implements (P6)."""

    def get(self, key: DiscoverKey) -> list[str] | None:
        """Return the cached preview for ``key`` if it is still within the window, else ``None``."""
        ...

    def put(self, key: DiscoverKey, words: list[str]) -> None:
        """Store ``words`` as the preview for ``key``, starting its reuse window now."""
        ...


class InProcessDiscoverCache:
    """A TTL reuse cache for discover previews held entirely in this process's memory.

    Each entry records the monotonic time it was stored; an entry is reusable while it is younger
    than ``ttl_seconds``. Every access first evicts entries that have aged out, and stores are
    re-inserted at the end so the dict stays in oldest-stored-first order — making both TTL eviction
    and the size cap a cheap pop from the front. The clock is injectable so tests fake time.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._max_entries = max_entries
        # Oldest-stored-first: ``put`` always (re)inserts at the end, so the front is always the
        # oldest entry — both expiry and the size cap pop from the front.
        self._entries: OrderedDict[DiscoverKey, tuple[float, list[str]]] = OrderedDict()

    def _evict_expired(self, now: float) -> None:
        """Drop entries older than the window. Front-to-back; stops at the first fresh one."""
        while self._entries:
            key, (stored_at, _) = next(iter(self._entries.items()))
            if now - stored_at >= self._ttl:
                self._entries.popitem(last=False)
            else:
                break

    def get(self, key: DiscoverKey) -> list[str] | None:
        """Return a copy of the cached preview for ``key`` when still fresh, else ``None``.

        Expired entries are evicted first, so a hit is always within the window. A *copy* is
        returned so a caller mutating the list can't corrupt the cached value.
        """
        now = self._clock()
        self._evict_expired(now)
        entry = self._entries.get(key)
        if entry is None:
            return None
        _, words = entry
        return list(words)

    def put(self, key: DiscoverKey, words: list[str]) -> None:
        """Cache ``words`` for ``key`` with the window starting now (bounded by the TTL + size cap).

        Stores a copy (so a later mutation of the caller's list doesn't change the cached value),
        re-inserts the key at the end to keep oldest-stored-first order, then enforces the size cap
        by evicting the oldest entries.
        """
        now = self._clock()
        self._evict_expired(now)
        self._entries[key] = (now, list(words))
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


@lru_cache(maxsize=1)
def _default_discover_cache() -> InProcessDiscoverCache:
    """The process-wide singleton cache, sized from settings (cached so it survives requests)."""
    return InProcessDiscoverCache(ttl_seconds=get_settings().discover_reuse_window_seconds)


def get_discover_cache() -> DiscoverCache:
    """FastAPI dependency: the process-wide :class:`DiscoverCache`.

    Returns the shared singleton so a preview stored by one request can be reused by the next (a
    fresh cache per request would never hit). Tests override this dependency with a fresh cache (and
    a fake clock) so the global store can't bleed between tests, mirroring ``get_rate_limiter``.
    """
    return _default_discover_cache()


def reset_discover_cache() -> None:
    """Drop the singleton so the next :func:`get_discover_cache` rebuilds it from settings."""
    _default_discover_cache.cache_clear()
