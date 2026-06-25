"""Task 1.2.2 — Groq ``generate_cards`` JSON parsing (no live network).

Feeds a recorded Groq JSON-mode payload through the pure parser and asserts a valid
``GeneratedCard`` list (including ``word_notes`` -> ``WordNote``), then drives the full
``generate_cards`` path through an injected fake client. ``disable_socket`` guarantees
nothing here touches the network.
"""

from __future__ import annotations

import json

import groq
import pytest

from lengua_core.llm import GeneratedCard, WordNote
from lengua_core.llm.groq import GroqProvider, parse_generated_cards
from tests.llm.fakes import FakeGroqClient

pytestmark = pytest.mark.disable_socket

# A recorded Groq chat-completion ``content`` string (JSON mode returns a JSON object).
RECORDED_CARDS = json.dumps(
    {
        "cards": [
            {
                "sentence": "La casa junto al río es enorme.",
                "translation": "The house by the river is huge.",
                "used_words": ["casa", "río"],
                "word_notes": [
                    {"word": "casa", "note": "house — the subject of the sentence."},
                    {"word": "río", "note": "river."},
                ],
            },
            {
                "sentence": "El perro ladra por la noche.",
                "translation": "The dog barks at night.",
                "used_words": ["perro"],
                "word_notes": [{"word": "perro", "note": "dog."}],
            },
        ]
    }
)


def test_parse_recorded_payload_into_cards() -> None:
    cards = parse_generated_cards(RECORDED_CARDS)
    assert len(cards) == 2
    assert all(isinstance(card, GeneratedCard) for card in cards)
    first = cards[0]
    assert first.sentence == "La casa junto al río es enorme."
    assert first.used_words == ["casa", "río"]
    assert isinstance(first.word_notes[0], WordNote)
    assert first.word_notes[0].word == "casa"
    assert first.word_notes[0].note.startswith("house")


def test_parse_bare_list_payload() -> None:
    payload = json.dumps([{"sentence": "Hola.", "translation": "Hi.", "used_words": []}])
    cards = parse_generated_cards(payload)
    assert len(cards) == 1
    assert cards[0].word_notes == []  # default empty when omitted


def test_parse_single_object_payload() -> None:
    payload = json.dumps({"sentence": "Hola.", "translation": "Hi.", "used_words": []})
    cards = parse_generated_cards(payload)
    assert len(cards) == 1
    assert cards[0].sentence == "Hola."


def test_parse_rejects_unexpected_shape() -> None:
    with pytest.raises(ValueError, match="not a JSON list of cards"):
        parse_generated_cards(json.dumps({"unexpected": 1}))


def test_parse_rejects_non_object_json() -> None:
    # A bare JSON scalar (not a list or object) is rejected, not silently accepted.
    with pytest.raises(ValueError, match="not a JSON list of cards"):
        parse_generated_cards(json.dumps(42))


def test_generate_cards_end_to_end_with_fake_client() -> None:
    client = FakeGroqClient(RECORDED_CARDS)
    provider = GroqProvider(api_key="x", model="llama-3.1-8b-instant", client=client)
    cards = provider.generate_cards(["casa", "río", "perro"], "Spanish", level_band="A2")
    assert len(cards) == 2
    assert client.completions.calls == 1


def test_generate_cards_empty_words_short_circuits() -> None:
    client = FakeGroqClient(RECORDED_CARDS)
    provider = GroqProvider(api_key="x", model="m", client=client)
    assert provider.generate_cards([], "Spanish") == []
    assert provider.generate_cards(["   ", ""], "Spanish") == []
    assert client.completions.calls == 0  # never reached the model


def test_builds_real_client_lazily_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no client injected, the provider builds groq.Groq lazily on first use,
    # passing the configured key — and reuses it thereafter.
    captured: dict[str, str] = {}

    def _factory(*, api_key: str) -> FakeGroqClient:
        captured["api_key"] = api_key
        return FakeGroqClient(RECORDED_CARDS)

    monkeypatch.setattr(groq, "Groq", _factory)
    provider = GroqProvider(api_key="gsk_lazy", model="llama-3.1-8b-instant")
    cards = provider.generate_cards(["casa"], "Spanish")
    assert len(cards) == 2
    assert captured["api_key"] == "gsk_lazy"
