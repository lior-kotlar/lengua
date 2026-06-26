"""Task 3.6.3 unit tests: the in-process discover reuse cache.

Exercises :class:`~app.discover_cache.InProcessDiscoverCache` directly with a faked clock — a hit
within the window, expiry once the window passes, key scoping, the bounded size cap (oldest first),
recency refresh on re-put, and the process-wide singleton dependency. No DB / HTTP.
"""

from __future__ import annotations

import uuid

from app.discover_cache import (
    DiscoverKey,
    InProcessDiscoverCache,
    get_discover_cache,
    reset_discover_cache,
)
from tests.quota.conftest import FakeClock


def _key(topic: str | None = "food", count: int = 5) -> DiscoverKey:
    """A distinct key (fresh user id) for the eviction/scoping tests."""
    return DiscoverKey(user_id=uuid.uuid4(), language_id=1, topic=topic, count=count)


def test_hit_within_window_then_expires() -> None:
    clock = FakeClock(1000.0)
    cache = InProcessDiscoverCache(ttl_seconds=300.0, clock=clock)
    key = _key()

    assert cache.get(key) is None  # empty → miss
    cache.put(key, ["a", "b"])
    assert cache.get(key) == ["a", "b"]  # within the window → hit

    clock.advance(299)
    assert cache.get(key) == ["a", "b"]  # still inside the window

    clock.advance(1)  # now exactly ttl old → expired and evicted
    assert cache.get(key) is None


def test_get_returns_a_copy() -> None:
    cache = InProcessDiscoverCache(ttl_seconds=300.0, clock=FakeClock(0.0))
    key = _key()
    cache.put(key, ["x"])

    got = cache.get(key)
    assert got == ["x"]
    got.append("mutated")  # mutating the returned list must not corrupt the cache

    assert cache.get(key) == ["x"]


def test_put_stores_a_copy() -> None:
    cache = InProcessDiscoverCache(ttl_seconds=300.0, clock=FakeClock(0.0))
    key = _key()
    words = ["x"]
    cache.put(key, words)
    words.append("mutated")  # mutating the caller's list after put must not change the cache

    assert cache.get(key) == ["x"]


def test_key_scoping() -> None:
    cache = InProcessDiscoverCache(ttl_seconds=300.0, clock=FakeClock(0.0))
    user = uuid.uuid4()
    cache.put(DiscoverKey(user_id=user, language_id=1, topic="food", count=5), ["food5"])

    # Different topic / count / language / user are all distinct keys → miss.
    assert cache.get(DiscoverKey(user_id=user, language_id=1, topic="travel", count=5)) is None
    assert cache.get(DiscoverKey(user_id=user, language_id=1, topic="food", count=3)) is None
    assert cache.get(DiscoverKey(user_id=user, language_id=2, topic="food", count=5)) is None
    other = uuid.uuid4()
    assert cache.get(DiscoverKey(user_id=other, language_id=1, topic="food", count=5)) is None

    # ``None`` topic and ``""`` topic are distinct keys (we key on the request value as sent).
    cache.put(DiscoverKey(user_id=user, language_id=1, topic=None, count=5), ["none"])
    assert cache.get(DiscoverKey(user_id=user, language_id=1, topic="", count=5)) is None
    assert cache.get(DiscoverKey(user_id=user, language_id=1, topic=None, count=5)) == ["none"]


def test_size_cap_evicts_oldest() -> None:
    clock = FakeClock(0.0)
    cache = InProcessDiscoverCache(ttl_seconds=10_000.0, clock=clock, max_entries=2)
    k1, k2, k3 = _key("t1"), _key("t2"), _key("t3")

    cache.put(k1, ["1"])
    clock.advance(1)
    cache.put(k2, ["2"])
    clock.advance(1)
    cache.put(k3, ["3"])  # exceeds max_entries=2 → the oldest-stored (k1) is evicted

    assert cache.get(k1) is None
    assert cache.get(k2) == ["2"]
    assert cache.get(k3) == ["3"]


def test_reput_refreshes_recency() -> None:
    """Re-putting a key moves it to newest, so it survives the size cap over an older entry."""
    clock = FakeClock(0.0)
    cache = InProcessDiscoverCache(ttl_seconds=10_000.0, clock=clock, max_entries=2)
    k1, k2, k3 = _key("t1"), _key("t2"), _key("t3")

    cache.put(k1, ["1"])
    clock.advance(1)
    cache.put(k2, ["2"])
    clock.advance(1)
    cache.put(k1, ["1b"])  # refresh k1 → now the newest
    clock.advance(1)
    cache.put(k3, ["3"])  # over cap → evicts the oldest remaining, which is now k2

    assert cache.get(k2) is None
    assert cache.get(k1) == ["1b"]
    assert cache.get(k3) == ["3"]


def test_singleton_dependency() -> None:
    reset_discover_cache()
    try:
        first = get_discover_cache()
        second = get_discover_cache()
        assert first is second  # process-wide singleton (survives across requests)
        assert isinstance(first, InProcessDiscoverCache)

        reset_discover_cache()
        assert get_discover_cache() is not first  # rebuilt from settings after a reset
    finally:
        reset_discover_cache()
