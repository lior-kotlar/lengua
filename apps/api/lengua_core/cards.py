"""Pure card-building: turn one generated sentence into a flashcard pair.

A generated sentence becomes **two** independently-scheduled flashcards — a *recognition* card
(target sentence -> English, for reading) and a *production* card (English -> target sentence,
to build it yourself). This module only builds the in-memory card pair; persistence (FSRS state,
due dates, INSERTs) lives in the legacy SQLite store and, for the API, in
``app/repositories/cards.py``.

It is **pure**: no database, no FSRS, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import GeneratedCard

__all__ = [
    "RECOGNITION",
    "PRODUCTION",
    "STRIP_CHARS",
    "BuiltCard",
    "bare_word",
    "build_cards",
]

# The two directions a sentence is studied in.
RECOGNITION = "recognition"  # front = target sentence, back = English (reading)
PRODUCTION = "production"  # front = English, back = target sentence (build it yourself)

# Punctuation trimmed off a token to get the "bare" word (incl. Arabic marks). Used both when
# keying stored explanations and when looking them up in the review page — the two MUST strip
# identically or lookups miss.
STRIP_CHARS = ".,!?؟،؛:;\"'«»…()[]"


def bare_word(token: str) -> str:
    """The word with surrounding punctuation stripped (diacritics kept)."""
    return token.strip(STRIP_CHARS)


@dataclass(frozen=True)
class BuiltCard:
    """One flashcard built from a generated sentence, ready to be persisted.

    ``word_explanations`` maps each meaningful word (bare form) to its note; it is only attached
    to the production card (whose back is the target sentence and which renders tap-a-word).
    """

    direction: str
    front: str
    back: str
    used_words: list[str]
    word_explanations: dict[str, str] | None
    gen_level: float | None


def build_cards(card: GeneratedCard, *, gen_level: float | None = None) -> list[BuiltCard]:
    """Build the recognition + production :class:`BuiltCard` pair for one generated sentence.

    ``gen_level`` is the learner's continuous CEFR score at generation time, tagged onto both
    cards so reviews only move the level when the card is current-level material. Returns exactly
    two cards: ``[recognition, production]``.
    """
    # Notes are keyed by bare word so the review page can look them up.
    notes = (
        {bare_word(n.word): n.note for n in card.word_notes} if card.word_notes else None
    )
    return [
        BuiltCard(
            direction=RECOGNITION,
            front=card.sentence,
            back=card.translation,
            used_words=card.used_words,
            word_explanations=None,
            gen_level=gen_level,
        ),
        BuiltCard(
            direction=PRODUCTION,
            front=card.translation,
            back=card.sentence,
            used_words=card.used_words,
            word_explanations=notes,
            gen_level=gen_level,
        ),
    ]
