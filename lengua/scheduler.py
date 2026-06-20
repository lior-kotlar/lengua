"""FSRS scheduling: fresh-card state, the daily due batch, and grading."""
import json
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

from . import config, proficiency
from .db import connect

_scheduler = Scheduler()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_card_state() -> tuple[str, str]:
    """Return (fsrs_state_json, due_iso) for a brand-new card (due immediately)."""
    card = Card()
    d = card.to_dict()
    return json.dumps(d), d["due"]


def is_new_card(card: dict) -> bool:
    """True if the card has never been reviewed — i.e. new since it was generated.

    New cards have no `last_review` in their FSRS state (freshly generated, and
    imported learning cards too); reviewed cards carry a `last_review` timestamp.
    """
    state = card.get("fsrs_state")
    return not (state and json.loads(state).get("last_review"))


def due_cards(language_id: int) -> list[dict]:
    """Saved cards for `language_id` that are due now, oldest-due first, capped by
    config limits. New cards (never reviewed) are limited separately so a big import
    doesn't bury reviews."""
    now = _now()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cards WHERE language_id = ? AND saved = 1 AND due IS NOT NULL",
            (language_id,),
        ).fetchall()

    due, new = [], []
    for r in rows:
        if datetime.fromisoformat(r["due"]) <= now:
            card = dict(r)
            (new if is_new_card(card) else due).append(card)

    due.sort(key=lambda c: c["due"])
    new.sort(key=lambda c: c["due"])
    batch = due + new[: config.DAILY_NEW_LIMIT]
    return batch[: config.DAILY_TOTAL_LIMIT]


def count_due(language_id: int) -> int:
    return len(due_cards(language_id))


def grade(card_id: int, rating: Rating) -> None:
    """Apply an FSRS rating to a card: update its state/due and log the review."""
    with connect() as conn:
        row = conn.execute(
            "SELECT fsrs_state, direction, gen_level, language_id FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if row is None:
            return
        card = Card.from_dict(json.loads(row["fsrs_state"]))
        card, _log = _scheduler.review_card(card, rating, review_datetime=_now())
        d = card.to_dict()
        conn.execute(
            "UPDATE cards SET fsrs_state = ?, due = ? WHERE id = ?",
            (json.dumps(d), d["due"], card_id),
        )
        conn.execute(
            "INSERT INTO reviews (card_id, rating) VALUES (?, ?)",
            (card_id, int(rating)),
        )
    # Nudge the language level from this answer (its own connection, after the commit).
    proficiency.register_review(
        row["language_id"], int(rating), row["direction"], row["gen_level"]
    )
