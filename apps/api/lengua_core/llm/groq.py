"""Groq provider — the default LLM backend for all dev and CI (tasks 1.2.2 / 1.2.3).

Groq exposes an OpenAI-compatible chat-completions API. We drive it through the
official ``groq`` SDK in JSON mode and parse the response into the same
:class:`~lengua_core.models.GeneratedCard` / :class:`~lengua_core.models.WordNote`
models the Gemini provider returns, so switching providers is a config flip
(``LLM_PROVIDER``) and never a code change.

The JSON-parsing helpers (:func:`parse_generated_cards`, :func:`parse_suggested_words`)
are deliberately pure module functions so they can be unit-tested against recorded
payloads with no network.
"""

from __future__ import annotations

import json
import os
from typing import Any

import groq

from lengua_core.models import GeneratedCard
from lengua_core.prompts import suggestion_instruction, system_instruction

from .keys import resolve_llm_key
from .retry import (
    EXPLAIN_MAX_TOKENS,
    GENERATE_MAX_TOKENS,
    SUGGEST_MAX_TOKENS,
    call_with_retry,
    cap_words,
)

DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

# HTTP statuses worth retrying (rate limit + transient server errors).
_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})

# Appended to the user message so the model returns a known JSON envelope. Groq's
# JSON mode (``response_format={"type": "json_object"}``) also requires the literal
# word "json" to appear somewhere in the prompt.
_CARDS_JSON_HINT = (
    '\n\nReturn a single JSON object of the form {"cards": [ ... ]}, where each '
    'element of "cards" is one item in exactly the format described above.'
)
_WORDS_JSON_HINT = (
    '\n\nReturn a single JSON object of the form {"words": ["word1", "word2", ...]} '
    "— a JSON array of the vocabulary word strings only, no other text."
)


def _is_transient(exc: BaseException) -> bool:
    """True for Groq errors worth retrying: 429/5xx, or connection/timeout blips."""
    if isinstance(exc, groq.APIConnectionError | groq.APITimeoutError):
        return True
    return getattr(exc, "status_code", None) in _TRANSIENT_STATUS


def _first_list(data: Any, keys: tuple[str, ...]) -> list[Any] | None:
    """Return ``data`` if it is a list, else the first list found under ``keys``."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return None


def parse_generated_cards(content: str) -> list[GeneratedCard]:
    """Parse a JSON chat-completion ``content`` string into ``GeneratedCard``s.

    Accepts a bare JSON array, an object wrapping the array under a common key
    (``cards`` / ``sentences`` / ...), or a lone card object, validating each
    element (including ``word_notes`` -> ``WordNote``) with Pydantic.
    """
    data = json.loads(content)
    items = _first_list(data, ("cards", "sentences", "items", "results", "data"))
    if items is None and isinstance(data, dict) and "sentence" in data:
        items = [data]  # a single card object, not wrapped in a list
    if items is None:
        raise ValueError("Groq generate_cards response was not a JSON list of cards")
    return [GeneratedCard.model_validate(item) for item in items]


def parse_suggested_words(content: str) -> list[str]:
    """Parse a JSON chat-completion ``content`` string into a list of word strings."""
    data = json.loads(content)
    items = _first_list(data, ("words", "suggestions", "vocabulary", "items", "results"))
    if items is None:
        raise ValueError("Groq suggest_new_words response was not a JSON list of words")
    return [str(word).strip() for word in items if str(word).strip()]


class GroqProvider:
    """An :class:`~lengua_core.llm.base.LLMProvider` backed by Groq's API."""

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        # Built lazily on first use (so construction does no I/O); injectable in tests.
        self._client = client

    @classmethod
    def from_env(cls) -> GroqProvider:
        """Build the Groq provider; the API key comes only from :func:`resolve_llm_key`.

        The key is obtained through the single key-resolution seam (task 3.9) — this class never
        reads the key env var itself — which fails fast with a clear error when it is unset. The
        model id still comes from ``GROQ_MODEL`` (a non-secret).
        """
        api_key = resolve_llm_key(provider="groq")
        return cls(api_key=api_key, model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))

    @property
    def model(self) -> str:
        """The Groq model id this provider sends requests to."""
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = groq.Groq(api_key=self._api_key)
        return self._client

    def _complete(
        self, system: str, user: str, *, max_tokens: int, json_mode: bool
    ) -> str:
        """Run one chat completion (with retry) and return the message text."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        def _call() -> str:
            resp = self._get_client().chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        return call_with_retry(_call, is_transient=_is_transient)

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        capped = cap_words(words)
        if not capped:
            return []
        system = system_instruction(language, vowelized=vowelized, level=level_band)
        user = (
            "Vocabulary words:\n"
            + "\n".join(f"- {w}" for w in capped)
            + _CARDS_JSON_HINT
        )
        content = self._complete(
            system, user, max_tokens=GENERATE_MAX_TOKENS, json_mode=True
        )
        return parse_generated_cards(content)

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        if count <= 0:
            return []
        system = suggestion_instruction(language, level_band, known_words, count, topic)
        user = f"Suggest {count} new {language} vocabulary words." + _WORDS_JSON_HINT
        content = self._complete(
            system, user, max_tokens=SUGGEST_MAX_TOKENS, json_mode=True
        )
        return parse_suggested_words(content)[:count]

    def explain_word(
        self, word: str, sentence: str, translation: str, language: str
    ) -> str:
        system = "You are a concise language tutor. Answer in at most two sentences."
        user = (
            f'In the {language} sentence: "{sentence}"\n'
            f'(English: "{translation}")\n\n'
            f'Briefly explain the word "{word}": its meaning and its role in this '
            f'sentence. Use at most two sentences; for a very simple or common word '
            f'(e.g. "to", "in", "and") a single word or short phrase is enough.'
        )
        text = self._complete(
            system, user, max_tokens=EXPLAIN_MAX_TOKENS, json_mode=False
        )
        if not text:
            raise RuntimeError("Groq returned an empty explanation; please try again.")
        return text
