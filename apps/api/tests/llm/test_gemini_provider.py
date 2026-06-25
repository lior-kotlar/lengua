"""Task 1.2.4 — the ported Gemini provider's methods, exercised offline.

Drives ``generate_cards`` / ``suggest_new_words`` / ``explain_word`` through an injected
fake ``google-genai`` client (the real ``response_schema`` config is still built, just no
network). ``disable_socket`` proves there is no I/O.
"""

from __future__ import annotations

import pytest
from google import genai

from lengua_core.llm import GeneratedCard, WordNote
from lengua_core.llm.gemini import GeminiProvider
from tests.llm.fakes import FakeGenaiClient, FakeGenaiResponse

pytestmark = pytest.mark.disable_socket


def _card() -> GeneratedCard:
    return GeneratedCard(
        sentence="La casa es grande.",
        translation="The house is big.",
        used_words=["casa"],
        word_notes=[WordNote(word="casa", note="house.")],
    )


def test_generate_cards_returns_parsed_schema_output() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(parsed=[_card()]))
    provider = GeminiProvider(api_key="k", model="gemini-2.5-flash", client=client)
    cards = provider.generate_cards(["casa"], "Spanish", vowelized=True, level_band="A2")
    assert len(cards) == 1
    assert cards[0].sentence == "La casa es grande."
    assert client.models.calls == 1


def test_generate_cards_empty_words_short_circuits() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(parsed=[_card()]))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    assert provider.generate_cards(["  "], "Spanish") == []
    assert client.models.calls == 0


def test_generate_cards_handles_none_parsed() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(parsed=None))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    assert provider.generate_cards(["casa"], "Spanish") == []


def test_suggest_new_words_truncates_to_count() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(parsed=["uno", "dos", "tres"]))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    assert provider.suggest_new_words("Spanish", "A2", [], count=2) == ["uno", "dos"]
    assert client.models.calls == 1


def test_suggest_new_words_zero_count_short_circuits() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(parsed=["uno"]))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    assert provider.suggest_new_words("Spanish", "A2", [], count=0) == []
    assert client.models.calls == 0


def test_explain_word_returns_text() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(text="  river — the place beside the house. "))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    assert provider.explain_word("río", "s", "t", "Spanish") == (
        "river — the place beside the house."
    )


def test_explain_word_empty_text_raises() -> None:
    client = FakeGenaiClient(FakeGenaiResponse(text="   "))
    provider = GeminiProvider(api_key="k", model="m", client=client)
    with pytest.raises(RuntimeError, match="empty explanation"):
        provider.explain_word("río", "s", "t", "Spanish")


def test_builds_real_client_lazily_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no client injected, the provider builds genai.Client lazily on first use,
    # passing the configured key.
    captured: dict[str, str] = {}

    def _factory(*, api_key: str) -> FakeGenaiClient:
        captured["api_key"] = api_key
        return FakeGenaiClient(FakeGenaiResponse(parsed=[_card()]))

    monkeypatch.setattr(genai, "Client", _factory)
    provider = GeminiProvider(api_key="gemini_lazy", model="gemini-2.5-flash")
    cards = provider.generate_cards(["casa"], "Spanish")
    assert len(cards) == 1
    assert captured["api_key"] == "gemini_lazy"
