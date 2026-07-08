"""Tasks 3.3.1 / 3.3.2 — per-user sliding-window rate limiting.

* :func:`test_window_counts` exercises :class:`~app.ratelimit.InProcessRateLimiter` directly with a
  faked clock: within one window the per-user counter increments, and once the window elapses it
  resets. No DB / HTTP — it proves the limiter's core sliding-window behaviour in isolation.
* :func:`test_blocks_over_limit` drives the gate end-to-end over HTTP: the ``(limit+1)``th gated
  call within the window returns **429** ``{"code": "rate_limited"}`` with a ``Retry-After`` header,
  and a later call after the window has elapsed is allowed again. The fake clock makes the window
  deterministic (no sleeping).
* :func:`test_reclaims_entry_when_all_timestamps_age_out` /
  :func:`test_disabled_limiter_does_not_accumulate_entries` prove the map is bounded on the
  *re-hit* path: an entry whose window empties (aged out, or a limit-0 limiter) is dropped rather
  than leaked per user id.
* :func:`test_max_keys_sweep_drops_only_expired_keys` proves the second bound for *one-shot* keys
  the re-hit reclaim never revisits: once the map outgrows ``max_keys`` the sweep reclaims every
  fully-expired key while sparing any key that still holds a live timestamp.
* :func:`test_sweep_spares_mixed_window_keys` pins the load-bearing predicate — a key with a *mixed*
  window (oldest timestamp expired, newest still live) survives the sweep and its retained live
  timestamp keeps counting against the limit (guards against sweeping on ``hits[0]`` — any-expired —
  instead of ``hits[-1]`` — fully-expired).
* :func:`test_sweep_never_evicts_live_keys_even_over_cap` pins the soft-bound invariant: an all-live
  map may legitimately exceed ``max_keys`` — live windows are never evicted to force the cap.
* :func:`test_sweep_hysteresis_limits_resweeps_to_once_per_window` proves the O(n) sweep runs at
  most once per window, so a sustained live-key flood can't turn it into a per-request CPU sink.
* :func:`test_map_stays_bounded_across_many_windows` soaks many multiples of ``max_keys`` one-shot
  keys across several windows and asserts a running size bound holds throughout.
* :func:`test_rejected_hit_over_cap_still_reports_correctly` checks a window-full rejection returns
  correct ``count``/``limit``/``retry_after`` even while the map is over cap.
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


def test_reclaims_entry_when_all_timestamps_age_out() -> None:
    """When a user's whole window ages out, its dict entry is reclaimed (bounded memory)."""
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=3, window_seconds=60.0, clock=clock)
    user = uuid.uuid4()

    # A first hit records a timestamp and creates the user's entry.
    assert limiter.hit(user).allowed is True
    assert user in limiter._hits
    original = limiter._hits[user]

    # Once the whole window has elapsed, the next hit finds every timestamp aged out: the empty
    # entry is reclaimed and then re-created for the fresh hit, so the stored deque is a NEW object
    # — proof the stale (empty) one was dropped from the map rather than left lingering.
    clock.advance(120)
    assert limiter.hit(user).count == 1
    assert limiter._hits[user] is not original


def test_disabled_limiter_does_not_accumulate_entries() -> None:
    """A limit of 0 rejects every hit without leaving a per-user entry behind.

    Even when hammered by many distinct user ids, the map stays empty — the reclaim keeps its size
    bounded rather than growing one permanent slot per id ever seen.
    """
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=0, window_seconds=60.0, clock=clock)
    for _ in range(100):
        assert limiter.hit(uuid.uuid4()).allowed is False
    assert len(limiter._hits) == 0


def test_max_keys_sweep_drops_only_expired_keys() -> None:
    """Once the map outgrows ``max_keys``, the sweep reclaims expired keys but spares live ones.

    The per-hit reclaim in :meth:`~app.ratelimit.InProcessRateLimiter.hit` only fires when a key is
    re-hit, so a flood of one-shot distinct keys (attacker-varied emails/IPs behind the public
    deletion-request limiters) would otherwise accumulate unbounded. When the map grows past
    ``max_keys`` the sweep drops every key whose window has fully aged out — without ever touching a
    key that still holds a live timestamp.
    """
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=5, window_seconds=60.0, clock=clock, max_keys=3)

    # Three one-shot keys, each hit exactly once and never revisited: the per-hit reclaim can't
    # touch them, so they simply accumulate (the map is allowed over max_keys until the next hit).
    old = [uuid.uuid4() for _ in range(3)]
    for key in old:
        assert limiter.hit(key).allowed is True
    assert len(limiter._hits) == 3

    # A fourth key recorded 30s in keeps a live timestamp once the older three have aged out.
    clock.advance(30)
    live = uuid.uuid4()
    assert limiter.hit(live).allowed is True
    assert len(limiter._hits) == 4  # over max_keys now; bounded lazily on the next hit

    # 35s more ages the three original windows out (65s old) but not ``live`` (35s old). The next
    # hit sees the map over max_keys and sweeps: the three expired keys go, ``live`` stays, and the
    # triggering key is recorded.
    clock.advance(35)
    trigger = uuid.uuid4()
    assert limiter.hit(trigger).allowed is True
    assert set(limiter._hits) == {live, trigger}
    assert all(key not in limiter._hits for key in old)


def test_sweep_spares_mixed_window_keys() -> None:
    """A key with a *mixed* window (oldest expired, newest live) survives the sweep, and its
    surviving timestamp keeps counting against the limit.

    This pins the load-bearing predicate: expiry is judged on the *newest* timestamp (``hits[-1]``,
    fully dead) — not the oldest (``hits[0]``, any-expired), which would drop a key that still holds
    a live request and so weaken a live window (the very regression the sweep must never cause).
    """
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=2, window_seconds=60.0, clock=clock, max_keys=2)

    # Build ``mixed``'s two-timestamp window while the map is at/under cap (so no premature sweep):
    # one hit now and one 50s later — both live when recorded.
    mixed = uuid.uuid4()
    assert limiter.hit(mixed).count == 1
    clock.advance(50)  # t=1050
    assert limiter.hit(mixed).count == 2  # mixed = [1000, 1050]

    # Two one-shot keys hit at t=1050 (still live at sweep time) pad the map past max_keys so the
    # next hit triggers a sweep.
    for _ in range(2):
        limiter.hit(uuid.uuid4())
    assert limiter._last_sweep is None
    assert len(limiter._hits) == 3

    # 15s on, ``mixed``'s oldest timestamp (1000) has aged out but its newest (1050) is still live —
    # a mixed window. The next over-cap hit sweeps (first sweep, so hysteresis allows it).
    clock.advance(15)  # t=1065; sweep cutoff = 1005: 1000 <= 1005 (dead), 1050 > 1005 (live)
    limiter.hit(uuid.uuid4())
    assert mixed in limiter._hits  # spared — judged fully-live on its newest timestamp

    # The retained live timestamp still occupies the window: mixed's next hit (its stale 1000 now
    # evicted per-hit) refills the second slot, so the following hit is rejected — proof 1050 was
    # kept through the sweep rather than silently dropped.
    refilled = limiter.hit(mixed)
    assert refilled.allowed is True
    assert refilled.count == 2  # surviving 1050 + this 1065
    blocked = limiter.hit(mixed)
    assert blocked.allowed is False
    assert blocked.count == 2


def test_sweep_never_evicts_live_keys_even_over_cap() -> None:
    """Live keys are never evicted — an all-live map may legitimately sit above ``max_keys``.

    The size cap is a floor that *triggers* a sweep of fully-expired keys, not a hard ceiling that
    evicts live windows: a hard-cap rewrite (sweep, then drop oldest-live until ``len <= max_keys``)
    would fail here.
    """
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=5, window_seconds=60.0, clock=clock, max_keys=3)

    live = [uuid.uuid4() for _ in range(5)]
    for key in live:
        assert limiter.hit(key).allowed is True

    # A sweep has already fired (the 5th hit saw the map over cap) and reclaimed nothing — every key
    # is live. Another hit keeps growing the map: live windows are held, never evicted for the cap.
    another = uuid.uuid4()
    limiter.hit(another)
    assert len(limiter._hits) == 6
    assert all(key in limiter._hits for key in live)
    assert another in limiter._hits


def test_sweep_hysteresis_limits_resweeps_to_once_per_window() -> None:
    """The O(n) sweep runs at most once per window — a sustained live-key flood can't thrash it.

    While the overflow is *live* keys the sweep reclaims nothing, so re-running it on every hit is
    pure wasted CPU on the event loop. A key that survived a sweep as live cannot fully expire until
    a window later, so the sweep is throttled to once per ``window_seconds``.
    """
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=5, window_seconds=60.0, clock=clock, max_keys=3)

    # Four live keys put the map over max_keys; the sweep only fires on the *next* over-cap hit.
    for _ in range(4):
        assert limiter.hit(uuid.uuid4()).allowed is True
    assert len(limiter._hits) == 4  # over cap, but no sweep has fired during the loop

    # That next over-cap hit sweeps (nothing to reclaim — all live) and records the sweep time.
    limiter.hit(uuid.uuid4())
    assert limiter._last_sweep == 1000.0
    assert len(limiter._hits) == 5  # live keys held; the map legitimately exceeds the cap

    # A second over-cap hit only 30s later is inside the window since the last sweep → it must NOT
    # re-sweep (nothing could have expired yet).
    clock.advance(30)  # t=1030
    kept_live = uuid.uuid4()
    limiter.hit(kept_live)
    assert limiter._last_sweep == 1000.0  # unchanged: no re-sweep within the window
    assert len(limiter._hits) == 6

    # Past one full window since the last sweep, the next over-cap hit sweeps again — the original
    # t=1000 keys have now aged out and are reclaimed, while ``kept_live`` (t=1030) survives.
    clock.advance(31)  # t=1061; 61s since the last sweep at 1000
    trigger = uuid.uuid4()
    limiter.hit(trigger)
    assert limiter._last_sweep == 1061.0  # re-swept
    assert set(limiter._hits) == {kept_live, trigger}


def test_map_stays_bounded_across_many_windows() -> None:
    """Soak: feeding many multiples of ``max_keys`` one-shot keys over several windows keeps the map
    bounded — its size never scales with the total number of keys ever seen.

    Without the sweep the map would grow to ``rounds * batch``; with it, each new window's first
    over-cap hit reclaims the previous window's now-expired batch, so the live size stays near one
    batch throughout.
    """
    clock = FakeClock(1000.0)
    max_keys, batch, rounds = 10, 30, 6
    limiter = InProcessRateLimiter(limit=5, window_seconds=60.0, clock=clock, max_keys=max_keys)

    for _ in range(rounds):
        for _ in range(batch):
            limiter.hit(uuid.uuid4())
            assert len(limiter._hits) <= batch + max_keys  # bounded after every single hit
        clock.advance(61)  # next window: the batch just added ages out

    assert len(limiter._hits) <= batch + max_keys  # not rounds * batch (== 180)


def test_rejected_hit_over_cap_still_reports_correctly() -> None:
    """A window-full rejection reports the right ``count``/``limit``/``retry_after`` even while the
    map is over ``max_keys`` and a sweep may run first."""
    clock = FakeClock(1000.0)
    limiter = InProcessRateLimiter(limit=2, window_seconds=60.0, clock=clock, max_keys=2)

    # Push the map over max_keys with distinct one-shot keys.
    for _ in range(3):
        limiter.hit(uuid.uuid4())
    assert len(limiter._hits) == 3

    # A "hot" key fills its own window, then its next hit is rejected — the rejection stays accurate
    # and the key is untouched despite the over-cap sweep path.
    hot = uuid.uuid4()
    assert limiter.hit(hot).count == 1
    assert limiter.hit(hot).count == 2
    blocked = limiter.hit(hot)
    assert blocked.allowed is False
    assert blocked.count == 2
    assert blocked.limit == 2
    assert blocked.retry_after >= 1
    assert hot in limiter._hits


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
