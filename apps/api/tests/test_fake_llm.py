"""Tests for the deterministic :class:`FakeLLM` (task 0.4.2).

Each test is marked ``disable_socket`` (pytest-socket) so any attempt to open a network
connection raises immediately — proving the fake does no I/O. Determinism is checked by calling
each method twice with identical arguments and asserting the results are equal.
"""

from __future__ import annotations

import pytest

from lengua_core.llm import GeneratedCard, LLMProvider, get_provider
from lengua_core.llm.base import LLMProvider as ProtocolForRuntimeCheck
from lengua_core.llm.fake import FakeLLM

pytestmark = pytest.mark.disable_socket


def test_fake_llm_satisfies_provider_protocol() -> None:
    fake = FakeLLM()
    # Structural typing: the fake is an LLMProvider without subclassing it.
    assert isinstance(fake, ProtocolForRuntimeCheck)


def test_get_provider_returns_fake_when_selected() -> None:
    provider: LLMProvider = get_provider("fake")
    assert isinstance(provider, FakeLLM)


def test_get_provider_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert isinstance(get_provider(), FakeLLM)


def test_get_provider_real_providers_not_implemented() -> None:
    for name in ("groq", "gemini"):
        with pytest.raises(NotImplementedError):
            get_provider(name)


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("nope")


def test_generate_cards_is_deterministic() -> None:
    fake = FakeLLM()
    args = (["casa", "perro"], "Spanish")
    first = fake.generate_cards(*args)
    second = fake.generate_cards(*args)
    assert first == second  # pure function of input — repeated calls are identical


def test_generate_cards_structure() -> None:
    cards = FakeLLM().generate_cards(["casa"], "Spanish", level_band="A2")
    assert len(cards) == 1
    card = cards[0]
    assert isinstance(card, GeneratedCard)
    assert "casa" in card.sentence
    assert "A2" in card.sentence  # the level band is threaded through deterministically
    assert card.translation
    assert card.used_words == ["casa"]
    assert card.word_notes and card.word_notes[0].word == "casa"


def test_generate_cards_vowelized_flag_reflected() -> None:
    plain = FakeLLM().generate_cards(["bayt"], "Arabic", vowelized=False)
    voweled = FakeLLM().generate_cards(["bayt"], "Arabic", vowelized=True)
    assert plain != voweled
    assert "(vowelized)" in voweled[0].sentence


def test_generate_cards_empty_input() -> None:
    assert FakeLLM().generate_cards([], "Spanish") == []
    assert FakeLLM().generate_cards(["  ", ""], "Spanish") == []


def test_suggest_new_words_is_deterministic_and_excludes_known() -> None:
    fake = FakeLLM()
    first = fake.suggest_new_words("Spanish", "A1", known_words=["house"], count=3)
    second = fake.suggest_new_words("Spanish", "A1", known_words=["house"], count=3)
    assert first == second
    assert len(first) == 3
    assert "house" not in [w.lower() for w in first]


def test_suggest_new_words_respects_count() -> None:
    fake = FakeLLM()
    assert fake.suggest_new_words("Spanish", "A1", [], count=5) == (
        fake.suggest_new_words("Spanish", "A1", [], count=5)
    )
    assert len(fake.suggest_new_words("Spanish", "A1", [], count=2)) == 2
    assert fake.suggest_new_words("Spanish", "A1", [], count=0) == []


def test_explain_word_is_deterministic() -> None:
    fake = FakeLLM()
    args = ("casa", "Vivo en una casa.", "I live in a house.", "Spanish")
    assert fake.explain_word(*args) == fake.explain_word(*args)


def test_explain_word_short_gloss_for_trivial_words() -> None:
    fake = FakeLLM()
    assert fake.explain_word("in", "Vivo en casa.", "I live at home.", "Spanish") == "in"
    full = fake.explain_word("casa", "Vivo en casa.", "I live at home.", "Spanish")
    assert "casa" in full and len(full) > len("casa")


def test_call_count_tracks_invocations() -> None:
    FakeLLM.reset_call_count()
    fake = FakeLLM()
    assert FakeLLM.call_count == 0
    fake.generate_cards(["casa"], "Spanish")
    fake.suggest_new_words("Spanish", "A1", [])
    fake.explain_word("casa", "s", "t", "Spanish")
    assert FakeLLM.call_count == 3
    FakeLLM.reset_call_count()
    assert FakeLLM.call_count == 0
