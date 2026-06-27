"""Product counters + gauges (task 5.2.5).

The cost-guard metrics (:mod:`app.llm_observability`) answer "are we about to get a bill?"; these
**product** metrics answer "are people learning and coming back?" — the server-side mirror of the
PostHog funnel (5.9, which is the authoritative, consent-gated product analytics). They are emitted
as plain OpenTelemetry instruments so they roll up into the Phase 5 **Product** dashboard (5.6.3):

* ``reviews_total`` — counter, +1 per graded review;
* ``cards_created_total`` — counter, +N per card-save (the number of cards persisted);
* ``signups_total`` — counter, +1 the first time the process serves a given user (see the caveat
  below);
* ``active_users`` — an observable gauge: distinct users seen within a recent rolling window.

**One shared meter provider.** These build their instruments from the single app-wide
:class:`~opentelemetry.sdk.metrics.MeterProvider` exposed by
:func:`app.llm_observability.get_meter_provider`, so product metrics, cost-guard metrics, and the
FastAPI RED histogram (5.2.6) all share one resource (``service.name`` + ``deployment.environment``)
and reader set, and the test in-memory reader (``install_test_meter_provider``) collects them too.
The instruments are rebuilt automatically if the provider is swapped (the tests do), so no
cross-module reset wiring is needed.

**Process-local caveat (Phase 6).** ``active_users`` (a rolling in-process set) + ``signups_total``
(a process-local "first seen" dedup) are *per-instance* — exactly like the in-process rate limiter
(:mod:`app.ratelimit`) and discover cache. On a single Cloud Run instance they are accurate; once
the service scales out or restarts they under/over-count, so Phase 6 moves the durable signals to
the DB / a shared store. ``signups_total`` is a coarse server-side proxy for "new account"; the
precise activation funnel is the consent-gated PostHog funnel (5.9.2). Documented in
``planning/outstanding-work.md`` §11.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from opentelemetry.metrics import CallbackOptions, Counter, MeterProvider, Observation

from app.llm_observability import get_meter_provider

#: Rolling window (seconds) over which a user counts as "active" for the ``active_users`` gauge.
#: 15 minutes — long enough to span a study session, short enough to mean "currently using it".
ACTIVE_USER_WINDOW_SECONDS = 900.0


class ActiveUsers:
    """Tracks distinct users seen within a rolling TTL window for the ``active_users`` gauge.

    A process-local ``{user_id: last_seen}`` map with an injectable monotonic clock. :meth:`mark`
    records activity; :meth:`count` prunes entries older than the window and returns the remainder.
    Thread-safe because the observable-gauge callback may run on a different thread from the request
    handlers that call :meth:`mark`.
    """

    def __init__(
        self,
        *,
        window_seconds: float = ACTIVE_USER_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window = window_seconds
        self._clock = clock
        self._seen: dict[uuid.UUID, float] = {}
        self._lock = threading.Lock()

    def mark(self, user_id: uuid.UUID) -> None:
        """Record that ``user_id`` was active now."""
        with self._lock:
            self._seen[user_id] = self._clock()

    def count(self) -> int:
        """Distinct users active within the window (prunes expired entries as a side effect)."""
        cutoff = self._clock() - self._window
        with self._lock:
            self._seen = {uid: seen for uid, seen in self._seen.items() if seen >= cutoff}
            return len(self._seen)

    def reset(self) -> None:
        """Forget all tracked users (test isolation)."""
        with self._lock:
            self._seen.clear()


@dataclass
class _Instruments:
    """The product metric instruments, bound to one meter (rebuilt if the provider is swapped)."""

    reviews_total: Counter
    cards_created_total: Counter
    signups_total: Counter


# Module-local state. ``_active_users`` (the rolling window) and ``_counted_signups`` (the
# "first seen this process" dedup) live independently of the meter provider, so they survive a
# test provider swap; the instruments are rebuilt whenever the provider changes (see _instruments).
_active_users = ActiveUsers()
_counted_signups: set[uuid.UUID] = set()
_signup_lock = threading.Lock()

_instruments_cache: _Instruments | None = None
_instruments_provider: MeterProvider | None = None


def _observe_active_users(options: CallbackOptions) -> Iterable[Observation]:
    """ObservableGauge callback: the current distinct active-user count."""
    yield Observation(_active_users.count())


def _instruments() -> _Instruments:
    """Return the product instruments, building them against the current shared meter provider.

    Rebuilds (and re-registers the ``active_users`` gauge) when the shared provider has changed
    since the last build — which is what lets the test in-memory provider (swapped via
    ``install_test_meter_provider``) collect these metrics with no explicit reset wiring.
    """
    global _instruments_cache, _instruments_provider
    provider = get_meter_provider()
    if _instruments_cache is None or _instruments_provider is not provider:
        meter = provider.get_meter("lengua.product")
        meter.create_observable_gauge(
            "active_users",
            callbacks=[_observe_active_users],
            description="Distinct users active within the recent rolling window.",
        )
        _instruments_cache = _Instruments(
            reviews_total=meter.create_counter(
                "reviews_total", description="Flashcards graded (reviews), all users."
            ),
            cards_created_total=meter.create_counter(
                "cards_created_total", description="Cards saved into decks, all users."
            ),
            signups_total=meter.create_counter(
                "signups_total", description="New users first seen by this process (proxy)."
            ),
        )
        _instruments_provider = provider
    return _instruments_cache


def record_review(user_id: uuid.UUID) -> None:
    """Count one graded review and mark ``user_id`` active."""
    _instruments().reviews_total.add(1)
    _active_users.mark(user_id)


def record_cards_created(user_id: uuid.UUID, count: int) -> None:
    """Count ``count`` newly-saved cards and mark ``user_id`` active (no-op when ``count <= 0``)."""
    if count <= 0:
        return
    _instruments().cards_created_total.add(count)
    _active_users.mark(user_id)


def record_signup(user_id: uuid.UUID) -> None:
    """Count a signup the first time this process sees ``user_id``, and mark them active.

    Deduplicated per process so repeated ``/me`` calls for the same user count once. A coarse
    server-side proxy for "new account" (the precise funnel is PostHog 5.9.2); see the module-level
    Phase-6 caveat. Always marks the user active so ``active_users`` reflects a just-arrived user.
    """
    with _signup_lock:
        first_seen = user_id not in _counted_signups
        if first_seen:
            _counted_signups.add(user_id)
    if first_seen:
        _instruments().signups_total.add(1)
    _active_users.mark(user_id)


def reset_product_metrics_state() -> None:
    """Clear the active-user window + the signup dedup (test isolation; not the counters)."""
    _active_users.reset()
    with _signup_lock:
        _counted_signups.clear()
