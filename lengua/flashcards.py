"""Persistence for generated cards / flashcards."""
import json

from . import scheduler
from .db import connect
from .models import GeneratedCard


def save_cards(
    language_id: int, cards: list[GeneratedCard], saved: bool = True
) -> int:
    """Insert generated cards. When `saved`, each card is initialized with FSRS
    state so it enters the review deck (due immediately). Returns rows inserted."""
    if not cards:
        return 0
    with connect() as conn:
        for c in cards:
            fsrs_state, due = scheduler.new_card_state() if saved else (None, None)
            conn.execute(
                "INSERT INTO cards (language_id, front, back, used_words, saved, "
                "fsrs_state, due) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    language_id,
                    c.sentence,
                    c.translation,
                    json.dumps(c.used_words),
                    1 if saved else 0,
                    fsrs_state,
                    due,
                ),
            )
    return len(cards)


def count_saved(language_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE language_id = ? AND saved = 1",
            (language_id,),
        ).fetchone()["n"]
