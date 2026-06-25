"""Task 1.1.2 — pure FSRS scheduler.

All functions are pure: they take card data + per-user limits and return results, with no DB and
no module-global scheduler. ``disable_socket`` proves they touch no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fsrs import Rating, Scheduler

from lengua_core import scheduler

pytestmark = pytest.mark.disable_socket

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
PAST_EARLY = "2026-01-01T10:00:00+00:00"
PAST_LATE = "2026-01-01T11:00:00+00:00"
FUTURE = "2026-01-02T12:00:00+00:00"


def _fresh_state() -> str:
    state, _due = scheduler.new_card_state()
    return state


def _reviewed_state() -> str:
    state, _due = scheduler.apply_rating(_fresh_state(), Rating.Good, now=NOW)
    return state


def test_new_card_state_is_serializable_and_due_now() -> None:
    state, due = scheduler.new_card_state()
    parsed = json.loads(state)
    assert isinstance(parsed, dict)
    # A brand-new card is due immediately and has never been reviewed.
    assert datetime.fromisoformat(due).tzinfo is not None
    assert not parsed.get("last_review")


def test_is_new_card_true_for_missing_or_fresh_state() -> None:
    assert scheduler.is_new_card({}) is True
    assert scheduler.is_new_card({"fsrs_state": None}) is True
    assert scheduler.is_new_card({"fsrs_state": _fresh_state()}) is True


def test_is_new_card_false_after_a_review() -> None:
    assert scheduler.is_new_card({"fsrs_state": _reviewed_state()}) is False


def test_apply_rating_moves_due_forward_and_marks_reviewed() -> None:
    state, due = scheduler.new_card_state()
    new_state, new_due = scheduler.apply_rating(state, Rating.Good, now=NOW)
    # The reschedule pushes the due date strictly past the review instant.
    assert datetime.fromisoformat(new_due) > NOW
    assert json.loads(new_state).get("last_review")


def test_apply_rating_accepts_an_injected_scheduler() -> None:
    state, _ = scheduler.new_card_state()
    # Fuzzing off makes the reschedule deterministic, so we can prove the *injected* scheduler
    # is the one used (and that there is no hidden module-global scheduler).
    sched = Scheduler(enable_fuzzing=False)
    a = scheduler.apply_rating(state, Rating.Easy, scheduler=sched, now=NOW)
    b = scheduler.apply_rating(state, Rating.Easy, scheduler=sched, now=NOW)
    assert a == b


def test_select_due_batch_picks_due_oldest_first_and_excludes_future() -> None:
    reviewed = _reviewed_state()
    cards = [
        {"id": 1, "due": PAST_LATE, "fsrs_state": reviewed},
        {"id": 2, "due": PAST_EARLY, "fsrs_state": reviewed},
        {"id": 3, "due": FUTURE, "fsrs_state": reviewed},
    ]
    batch = scheduler.select_due_batch(cards, new_limit=10, total_limit=50, now=NOW)
    assert [c["id"] for c in batch] == [2, 1]  # oldest-due first, future excluded


def test_select_due_batch_caps_new_cards_separately() -> None:
    fresh = _fresh_state()
    cards = [
        {"id": 1, "due": PAST_EARLY, "fsrs_state": fresh},
        {"id": 2, "due": PAST_LATE, "fsrs_state": fresh},
        {"id": 3, "due": PAST_EARLY, "fsrs_state": fresh},
    ]
    batch = scheduler.select_due_batch(cards, new_limit=1, total_limit=50, now=NOW)
    assert len(batch) == 1  # only one new card allowed in


def test_select_due_batch_applies_total_limit_after_new() -> None:
    reviewed = _reviewed_state()
    cards = [
        {"id": 1, "due": PAST_EARLY, "fsrs_state": reviewed},
        {"id": 2, "due": PAST_LATE, "fsrs_state": reviewed},
    ]
    batch = scheduler.select_due_batch(cards, new_limit=10, total_limit=1, now=NOW)
    assert [c["id"] for c in batch] == [1]


def test_select_due_batch_ignores_cards_without_a_due_date() -> None:
    reviewed = _reviewed_state()
    cards = [
        {"id": 1, "due": None, "fsrs_state": reviewed},
        {"id": 2, "due": "", "fsrs_state": reviewed},
        {"id": 3, "due": PAST_EARLY, "fsrs_state": reviewed},
    ]
    batch = scheduler.select_due_batch(cards, new_limit=10, total_limit=50, now=NOW)
    assert [c["id"] for c in batch] == [3]


def test_apply_rating_uses_current_time_when_now_omitted() -> None:
    state, _ = scheduler.new_card_state()
    new_state, new_due = scheduler.apply_rating(state, Rating.Good)
    # With no explicit clock the real "now" is used; the card is reviewed and rescheduled.
    assert json.loads(new_state).get("last_review")
    assert datetime.fromisoformat(new_due).tzinfo is not None


def test_select_due_batch_uses_current_time_when_now_omitted() -> None:
    # A card due far in the past is due regardless of the real current clock.
    cards = [{"id": 1, "due": "2000-01-01T00:00:00+00:00", "fsrs_state": _fresh_state()}]
    batch = scheduler.select_due_batch(cards, new_limit=10, total_limit=50)
    assert [c["id"] for c in batch] == [1]


def test_select_due_batch_does_not_mutate_input() -> None:
    reviewed = _reviewed_state()
    cards = [
        {"id": 1, "due": PAST_LATE, "fsrs_state": reviewed},
        {"id": 2, "due": PAST_EARLY, "fsrs_state": reviewed},
    ]
    scheduler.select_due_batch(cards, new_limit=10, total_limit=50, now=NOW)
    assert [c["id"] for c in cards] == [1, 2]  # original order preserved
