"""Persistence for generated cards / flashcards."""
import json

from . import scheduler
from .db import connect
from .models import GeneratedCard

# A generated sentence becomes two independently-scheduled flashcards:
RECOGNITION = "recognition"  # front = target sentence, back = English (reading)
PRODUCTION = "production"     # front = English, back = target sentence (build it yourself)

# Punctuation trimmed off a token to get the "bare" word (incl. Arabic marks). Used
# both when keying stored explanations and when looking them up in the review page —
# the two MUST strip identically or lookups miss.
STRIP_CHARS = ".,!?؟،؛:;\"'«»…()[]"


def bare_word(token: str) -> str:
    """The word with surrounding punctuation stripped (diacritics kept)."""
    return token.strip(STRIP_CHARS)


def save_cards(
    language_id: int,
    cards: list[GeneratedCard],
    saved: bool = True,
    gen_level: float | None = None,
) -> int:
    """Insert generated cards. Each sentence is saved as TWO flashcards — a
    recognition card (target->English) and a production card (English->target) — each
    with its own FSRS state so they are scheduled independently. When `saved`, both
    enter the review deck (due immediately). `gen_level` is the learner's continuous
    CEFR score at generation time, stored so reviews only move the level when the card
    is current-level material. Returns the number of sentences saved."""
    if not cards:
        return 0
    with connect() as conn:
        for c in cards:
            used = json.dumps(c.used_words)
            # Notes are keyed by bare word so the review page can look them up; only the
            # production card (back = target sentence) renders tap-a-word.
            notes = (
                json.dumps({bare_word(n.word): n.note for n in c.word_notes})
                if c.word_notes
                else None
            )
            for direction, front, back, explanations in (
                (RECOGNITION, c.sentence, c.translation, None),
                (PRODUCTION, c.translation, c.sentence, notes),
            ):
                fsrs_state, due = scheduler.new_card_state() if saved else (None, None)
                conn.execute(
                    "INSERT INTO cards (language_id, front, back, used_words, saved, "
                    "fsrs_state, due, direction, word_explanations, gen_level) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        language_id,
                        front,
                        back,
                        used,
                        1 if saved else 0,
                        fsrs_state,
                        due,
                        direction,
                        explanations,
                        gen_level,
                    ),
                )
    return len(cards)


def save_word_explanation(card_id: int, word: str, note: str) -> None:
    """Persist one tapped-word explanation into the card's stored notes (lazy cache)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT word_explanations FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        if row is None:
            return
        notes = json.loads(row["word_explanations"]) if row["word_explanations"] else {}
        notes[bare_word(word)] = note
        conn.execute(
            "UPDATE cards SET word_explanations = ? WHERE id = ?",
            (json.dumps(notes), card_id),
        )


def count_saved(language_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE language_id = ? AND saved = 1",
            (language_id,),
        ).fetchone()["n"]


def get_known_words(language_id: int) -> list[str]:
    """Return a deduplicated sorted list of every vocabulary word the user has a saved card for."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT used_words FROM cards WHERE language_id = ? AND saved = 1 AND used_words IS NOT NULL",
            (language_id,),
        ).fetchall()
    words: set[str] = set()
    for row in rows:
        words.update(json.loads(row["used_words"]))
    return sorted(words)
