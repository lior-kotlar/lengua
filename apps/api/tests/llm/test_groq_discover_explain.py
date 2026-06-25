"""Task 1.2.3 — Groq ``suggest_new_words`` (-> list[str]) and ``explain_word`` (-> str).

Parses recorded responses into a word list and an explanation string, and drives both
methods through an injected fake client (no network — ``disable_socket``).
"""

from __future__ import annotations

import json

import pytest

from lengua_core.llm.groq import GroqProvider, parse_suggested_words
from tests.llm.fakes import FakeGroqClient

pytestmark = pytest.mark.disable_socket

RECORDED_WORDS = json.dumps({"words": ["mañana", "biblioteca", "tren", "ventana"]})
RECORDED_EXPLANATION = "“río” means “river”; here it is the place the house sits beside."


def test_parse_recorded_words_object() -> None:
    words = parse_suggested_words(RECORDED_WORDS)
    assert words == ["mañana", "biblioteca", "tren", "ventana"]


def test_parse_bare_list_of_words() -> None:
    words = parse_suggested_words(json.dumps(["uno", "dos", "  ", "tres"]))
    assert words == ["uno", "dos", "tres"]  # blanks dropped


def test_parse_rejects_unexpected_words_shape() -> None:
    with pytest.raises(ValueError, match="not a JSON list of words"):
        parse_suggested_words(json.dumps({"nope": True}))


def test_suggest_new_words_end_to_end_truncates_to_count() -> None:
    client = FakeGroqClient(RECORDED_WORDS)
    provider = GroqProvider(api_key="x", model="m", client=client)
    words = provider.suggest_new_words("Spanish", "A2", known_words=["casa"], count=2)
    assert words == ["mañana", "biblioteca"]  # capped to count
    assert client.completions.calls == 1


def test_suggest_new_words_zero_count_short_circuits() -> None:
    client = FakeGroqClient(RECORDED_WORDS)
    provider = GroqProvider(api_key="x", model="m", client=client)
    assert provider.suggest_new_words("Spanish", "A2", [], count=0) == []
    assert client.completions.calls == 0


def test_explain_word_returns_text() -> None:
    client = FakeGroqClient(RECORDED_EXPLANATION)
    provider = GroqProvider(api_key="x", model="m", client=client)
    explanation = provider.explain_word("río", "La casa junto al río.", "...", "Spanish")
    assert explanation == RECORDED_EXPLANATION
    assert client.completions.calls == 1


def test_explain_word_empty_response_raises() -> None:
    client = FakeGroqClient("   ")  # whitespace-only -> treated as empty
    provider = GroqProvider(api_key="x", model="m", client=client)
    with pytest.raises(RuntimeError, match="empty explanation"):
        provider.explain_word("río", "s", "t", "Spanish")
