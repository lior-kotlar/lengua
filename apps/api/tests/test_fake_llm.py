"""Tests for the deterministic, offline FakeLLM provider."""

import socket

import pytest

from lengua_core.llm import FakeLLM, LLMProvider
from lengua_core.models import GeneratedCard, WordNote


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


def test_fake_llm_satisfies_provider_interface(llm: FakeLLM) -> None:
    assert isinstance(llm, LLMProvider)


def test_generate_cards_shape_and_determinism(llm: FakeLLM) -> None:
    first = llm.generate_cards(["hola", "gato"], language="Spanish")
    second = llm.generate_cards(["hola", "gato"], language="Spanish")

    assert first == second  # identical structured output across repeated calls
    assert [type(card) for card in first] == [GeneratedCard, GeneratedCard]
    assert first[0].used_words == ["hola"]
    assert isinstance(first[0].word_notes[0], WordNote)


def test_generate_cards_skips_blank_words_and_marks_vowelized(llm: FakeLLM) -> None:
    cards = llm.generate_cards([" hola ", "", "  "], language="Arabic", vowelized=True)

    assert len(cards) == 1
    assert cards[0].used_words == ["hola"]
    assert "Arabic+vowels" in cards[0].sentence


def test_suggest_new_words_is_deterministic_and_excludes_known(llm: FakeLLM) -> None:
    known = ["spanish-a2-word-1", "spanish-a2-word-2"]
    first = llm.suggest_new_words("Spanish", "A2", known, count=3)
    second = llm.suggest_new_words("Spanish", "A2", known, count=3)

    assert first == second
    assert len(first) == 3
    assert not set(first) & set(known)


def test_explain_word_is_deterministic_and_nonempty(llm: FakeLLM) -> None:
    args = ("gato", "El gato duerme.", "The cat sleeps.", "Spanish")
    assert llm.explain_word(*args) == llm.explain_word(*args)
    assert llm.explain_word(*args).strip()


def test_fake_llm_makes_no_network_calls(llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("FakeLLM must not open a socket")

    monkeypatch.setattr(socket, "socket", _no_network)

    # All three methods must work with sockets disabled.
    assert llm.generate_cards(["x"], language="Spanish")
    assert llm.suggest_new_words("Spanish", "A1", [], count=1)
    assert llm.explain_word("x", "X.", "X.", "Spanish")
