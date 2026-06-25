"""Pure FSRS scheduling helpers: fresh-card state, due-batch selection, and grading.

Every function here is a pure transformation: callers pass in the card data (FSRS state as
JSON, the candidate cards, per-user limits) and get results back. There is **no database
access and no module-global scheduler** — a :class:`fsrs.Scheduler` is constructed locally (or
accepted as an argument), so the same FSRS algorithm config can be threaded through without
hidden global state.

The legacy SQLite orchestration that reads/writes these results lives in
:mod:`legacy_streamlit.store`; the FastAPI service + repositories (Phase 1.3+) wire them into
Postgres. Both layers depend only on the functions below.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

__all__ = [
    "new_card_state",
    "is_new_card",
    "select_due_batch",
    "apply_rating",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_card_state() -> tuple[str, str]:
    """Return ``(fsrs_state_json, due_iso)`` for a brand-new card (due immediately)."""
    card = Card()
    d = card.to_dict()
    return json.dumps(d), d["due"]


def is_new_card(card: dict) -> bool:
    """True if the card has never been reviewed — i.e. new since it was generated.

    New cards have no ``last_review`` in their FSRS state (freshly generated, and imported
    learning cards too); reviewed cards carry a ``last_review`` timestamp.
    """
    state = card.get("fsrs_state")
    return not (state and json.loads(state).get("last_review"))


def select_due_batch(
    cards: list[dict],
    *,
    new_limit: int,
    total_limit: int,
    now: datetime | None = None,
) -> list[dict]:
    """Pick the cards due as of ``now``, oldest-due first, capped by the given limits.

    ``cards`` are the candidate saved cards (each a mapping with ``due`` — an ISO-8601 string
    — and ``fsrs_state``). New cards (never reviewed) are limited separately by ``new_limit``
    so a big import doesn't bury reviews; the combined batch is then capped at ``total_limit``.
    Pure: no I/O, and the input list is not mutated.
    """
    cutoff = now or _now()
    due: list[dict] = []
    new: list[dict] = []
    for card in cards:
        due_at = card.get("due")
        if not due_at:
            continue
        if datetime.fromisoformat(due_at) <= cutoff:
            (new if is_new_card(card) else due).append(card)

    due.sort(key=lambda c: c["due"])
    new.sort(key=lambda c: c["due"])
    batch = due + new[:new_limit]
    return batch[:total_limit]


def apply_rating(
    fsrs_state: str,
    rating: Rating,
    *,
    scheduler: Scheduler | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Apply an FSRS ``rating`` to a card's serialized state.

    Returns the new ``(fsrs_state_json, due_iso)``. A :class:`fsrs.Scheduler` is created locally
    when one isn't supplied, so there is no shared mutable global. Persisting the result (and
    logging the review) is the caller's job.
    """
    sched = scheduler or Scheduler()
    card = Card.from_dict(json.loads(fsrs_state))
    card, _log = sched.review_card(card, rating, review_datetime=now or _now())
    d = card.to_dict()
    return json.dumps(d), d["due"]
