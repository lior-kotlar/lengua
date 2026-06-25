"""Task 1.1.1 — the ``lengua_core`` package root re-exports the shared models.

Proves ``from lengua_core import GeneratedCard, WordNote`` works and that the re-exports are the
very same classes defined in :mod:`lengua_core.models` (a single import surface for the seam).
"""

from __future__ import annotations

import lengua_core
from lengua_core import GeneratedCard, WordNote
from lengua_core.models import GeneratedCard as ModelGeneratedCard
from lengua_core.models import WordNote as ModelWordNote


def test_root_reexports_are_the_model_classes() -> None:
    assert GeneratedCard is ModelGeneratedCard
    assert WordNote is ModelWordNote


def test_root_all_lists_exactly_the_models() -> None:
    assert set(lengua_core.__all__) == {"GeneratedCard", "WordNote"}


def test_reexported_models_construct_and_validate() -> None:
    card = GeneratedCard(
        sentence="Hola, ¿cómo estás?",
        translation="Hello, how are you?",
        used_words=["hola"],
        word_notes=[WordNote(word="hola", note="a greeting")],
    )
    assert card.used_words == ["hola"]
    assert card.word_notes[0].word == "hola"
    # word_notes defaults to an empty list when omitted.
    assert GeneratedCard(sentence="x", translation="y", used_words=[]).word_notes == []
