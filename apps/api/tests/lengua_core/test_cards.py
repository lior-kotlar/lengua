"""Task 1.1.4 — pure card-building.

One :class:`GeneratedCard` yields a recognition + production card pair, tagged with the
generation level. No SQLite, no FSRS. ``disable_socket`` proves no I/O.
"""

from __future__ import annotations

import pytest

from lengua_core import cards
from lengua_core.models import GeneratedCard, WordNote

pytestmark = pytest.mark.disable_socket


def _generated() -> GeneratedCard:
    return GeneratedCard(
        sentence="El perro corre.",
        translation="The dog runs.",
        used_words=["perro", "correr"],
        word_notes=[
            WordNote(word="perro.", note="dog"),
            WordNote(word="corre", note="runs (correr)"),
        ],
    )


def test_one_generated_card_yields_recognition_and_production_pair() -> None:
    built = cards.build_cards(_generated(), gen_level=2.0)
    assert len(built) == 2
    assert [c.direction for c in built] == [cards.RECOGNITION, cards.PRODUCTION]


def test_recognition_card_is_target_to_english_without_notes() -> None:
    recognition, _production = cards.build_cards(_generated(), gen_level=2.0)
    assert recognition.front == "El perro corre."  # target sentence
    assert recognition.back == "The dog runs."  # English
    assert recognition.word_explanations is None  # notes only on production


def test_production_card_is_english_to_target_with_bare_keyed_notes() -> None:
    _recognition, production = cards.build_cards(_generated(), gen_level=2.0)
    assert production.front == "The dog runs."  # English prompt
    assert production.back == "El perro corre."  # build the target
    # Notes are keyed by the *bare* word (punctuation stripped) for review-page lookups.
    assert production.word_explanations == {"perro": "dog", "corre": "runs (correr)"}


def test_gen_level_is_tagged_on_both_cards() -> None:
    built = cards.build_cards(_generated(), gen_level=3.5)
    assert all(c.gen_level == 3.5 for c in built)
    # Defaults to None when not supplied (legacy/imported cards).
    assert all(c.gen_level is None for c in cards.build_cards(_generated()))


def test_used_words_preserved_on_both_cards() -> None:
    for card in cards.build_cards(_generated()):
        assert card.used_words == ["perro", "correr"]


def test_no_word_notes_means_no_production_explanations() -> None:
    plain = GeneratedCard(sentence="Hola.", translation="Hi.", used_words=["hola"])
    _recognition, production = cards.build_cards(plain)
    assert production.word_explanations is None


def test_bare_word_strips_surrounding_punctuation_keeping_diacritics() -> None:
    assert cards.bare_word("perro.") == "perro"
    assert cards.bare_word("«Hola»!") == "Hola"
    assert cards.bare_word("(test)") == "test"
    # Arabic diacritics are kept; only the trailing punctuation mark is stripped.
    assert cards.bare_word("بَيْت،") == "بَيْت"


def test_fold_word_is_case_and_diacritic_insensitive() -> None:
    # Case + Latin accents fold together: all three are the same folded form.
    assert cards.fold_word("Está") == cards.fold_word("esta") == cards.fold_word("ESTÁ") == "esta"
    # Surrounding punctuation is stripped before folding.
    assert cards.fold_word("«Está».") == "esta"
    # A vowel-marked (niqqud) Hebrew surface folds to its bare consonant skeleton.
    assert cards.fold_word("שָׁלוֹם") == cards.fold_word("שלום")
    # An Arabic harakat-marked surface folds to its bare form.
    assert cards.fold_word("مَدْرَسَة") == cards.fold_word("مدرسة")
    # An all-punctuation token folds to empty (never matches anything).
    assert cards.fold_word("...") == ""
