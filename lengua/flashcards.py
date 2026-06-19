"""Persistence for generated cards / flashcards."""
import json

from . import scheduler
from .db import connect
from .models import GeneratedCard

# A generated sentence becomes two independently-scheduled flashcards:
RECOGNITION = "recognition"  # front = target sentence, back = English (reading)
PRODUCTION = "production"     # front = English, back = target sentence (build it yourself)


def save_cards(
    language_id: int, cards: list[GeneratedCard], saved: bool = True
) -> int:
    """Insert generated cards. Each sentence is saved as TWO flashcards — a
    recognition card (target->English) and a production card (English->target) — each
    with its own FSRS state so they are scheduled independently. When `saved`, both
    enter the review deck (due immediately). Returns the number of sentences saved."""
    if not cards:
        return 0
    with connect() as conn:
        for c in cards:
            used = json.dumps(c.used_words)
            for direction, front, back in (
                (RECOGNITION, c.sentence, c.translation),
                (PRODUCTION, c.translation, c.sentence),
            ):
                fsrs_state, due = scheduler.new_card_state() if saved else (None, None)
                conn.execute(
                    "INSERT INTO cards (language_id, front, back, used_words, saved, "
                    "fsrs_state, due, direction) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        language_id,
                        front,
                        back,
                        used,
                        1 if saved else 0,
                        fsrs_state,
                        due,
                        direction,
                    ),
                )
    return len(cards)


def count_saved(language_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE language_id = ? AND saved = 1",
            (language_id,),
        ).fetchone()["n"]
