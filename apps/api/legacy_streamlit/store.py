"""Legacy SQLite persistence + orchestration for the Streamlit app.

This module is the legacy app's single persistence facade. It wires the **pure** domain logic in
:mod:`lengua_core` (FSRS scheduling, proficiency scoring, card building) to the legacy SQLite
database, and re-exports the handful of pure helpers the pages also use (``is_new_card``,
``bare_word``, the ``RECOGNITION`` / ``PRODUCTION`` direction constants) so a page only needs to
import :mod:`legacy_streamlit.store`.

Keeping all SQL here means ``lengua_core`` carries no database code; the FastAPI service grows an
equivalent Postgres repository layer in Phase 1.3.
"""

from __future__ import annotations

import json

from fsrs import Rating

from lengua_core import cards as core_cards
from lengua_core import config, proficiency, scheduler
from lengua_core.cards import PRODUCTION, RECOGNITION, bare_word
from lengua_core.models import GeneratedCard
from lengua_core.scheduler import is_new_card, new_card_state

from . import settings as app_settings
from .db import connect

__all__ = [
    "RECOGNITION",
    "PRODUCTION",
    "bare_word",
    "is_new_card",
    "new_card_state",
    "due_cards",
    "count_due",
    "grade",
    "save_cards",
    "save_word_explanation",
    "count_saved",
    "get_known_words",
    "get_score",
    "set_score",
    "get_band",
    "set_band",
]


# ── Review batch + grading (FSRS) ──────────────────────────────────────────────────
def due_cards(language_id: int) -> list[dict]:
    """Saved cards for ``language_id`` due now, oldest-due first, capped by the user's limits."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cards WHERE language_id = ? AND saved = 1 AND due IS NOT NULL",
            (language_id,),
        ).fetchall()
    candidates = [dict(r) for r in rows]
    return scheduler.select_due_batch(
        candidates,
        new_limit=app_settings.daily_new_limit(),
        total_limit=app_settings.daily_total_limit(),
    )


def count_due(language_id: int) -> int:
    return len(due_cards(language_id))


def grade(card_id: int, rating: Rating) -> None:
    """Apply an FSRS rating to a card: update its state/due, log the review, nudge the level."""
    with connect() as conn:
        row = conn.execute(
            "SELECT fsrs_state, direction, gen_level, language_id FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if row is None:
            return
        fsrs_state, due = scheduler.apply_rating(row["fsrs_state"], rating)
        conn.execute(
            "UPDATE cards SET fsrs_state = ?, due = ? WHERE id = ?",
            (fsrs_state, due, card_id),
        )
        conn.execute(
            "INSERT INTO reviews (card_id, rating) VALUES (?, ?)",
            (card_id, int(rating)),
        )

    # Nudge the language level from this answer (its own connection, after the commit).
    current = get_score(row["language_id"])
    new_score = proficiency.register_review(
        current, int(rating), row["direction"], row["gen_level"]
    )
    if new_score != current:
        set_score(row["language_id"], new_score)


# ── Card persistence ───────────────────────────────────────────────────────────────
def save_cards(
    language_id: int,
    cards: list[GeneratedCard],
    saved: bool = True,
    gen_level: float | None = None,
) -> int:
    """Persist generated sentences as flashcards (two per sentence). Returns the sentence count.

    Each sentence becomes a recognition card (target->English) and a production card
    (English->target), each with its own FSRS state so they schedule independently. When
    ``saved``, both enter the review deck (due immediately). ``gen_level`` is stored so reviews
    only move the level for current-level material.
    """
    if not cards:
        return 0
    with connect() as conn:
        for card in cards:
            for built in core_cards.build_cards(card, gen_level=gen_level):
                used = json.dumps(built.used_words)
                notes = (
                    json.dumps(built.word_explanations)
                    if built.word_explanations
                    else None
                )
                fsrs_state, due = new_card_state() if saved else (None, None)
                conn.execute(
                    "INSERT INTO cards (language_id, front, back, used_words, saved, "
                    "fsrs_state, due, direction, word_explanations, gen_level) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        language_id,
                        built.front,
                        built.back,
                        used,
                        1 if saved else 0,
                        fsrs_state,
                        due,
                        built.direction,
                        notes,
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
    """Deduplicated, sorted list of every vocabulary word the user has a saved card for."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT used_words FROM cards "
            "WHERE language_id = ? AND saved = 1 AND used_words IS NOT NULL",
            (language_id,),
        ).fetchall()
    words: set[str] = set()
    for row in rows:
        words.update(json.loads(row["used_words"]))
    return sorted(words)


# ── Proficiency persistence ─────────────────────────────────────────────────────────
def get_score(language_id: int, user_id: int = config.DEFAULT_USER_ID) -> float:
    """The learner's continuous score for a language (0.0 / A1 if not set yet)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT score FROM proficiency WHERE user_id = ? AND language_id = ?",
            (user_id, language_id),
        ).fetchone()
    return float(row["score"]) if row else config.LEVEL_MIN


def set_score(
    language_id: int, score: float, user_id: int = config.DEFAULT_USER_ID
) -> float:
    """Upsert the clamped score and return the stored value."""
    score = proficiency.clamp_score(score)
    with connect() as conn:
        conn.execute(
            "INSERT INTO proficiency (user_id, language_id, score) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, language_id) DO UPDATE SET "
            "score = excluded.score, updated_at = datetime('now')",
            (user_id, language_id, score),
        )
    return score


def get_band(language_id: int, user_id: int = config.DEFAULT_USER_ID) -> str:
    return proficiency.band_for_score(get_score(language_id, user_id))


def set_band(
    language_id: int, band: str, user_id: int = config.DEFAULT_USER_ID
) -> float:
    """Manually place the learner at a CEFR band (sets the score to its lower bound)."""
    return set_score(language_id, proficiency.score_for_band(band), user_id)
