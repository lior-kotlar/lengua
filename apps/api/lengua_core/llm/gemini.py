"""Gemini provider behind the shared LLM seam (task 1.2.4).

A port of the legacy ``lengua_core.gemini`` wrapper to the
:class:`~lengua_core.llm.base.LLMProvider` Protocol, selectable with
``LLM_PROVIDER=gemini`` (reserved for prod / prompt validation). The generation
logic is unchanged from the legacy module — native ``response_schema`` parsing for
structured output — but transient retries now flow through the shared
:func:`~lengua_core.llm.retry.call_with_retry` helper and the request caps are
applied at the call boundary.

The legacy ``lengua_core.gemini`` module is left in place, still imported by the
legacy Streamlit app; this is the seam implementation the FastAPI service uses.
"""

from __future__ import annotations

import os
from typing import Any

from google import genai
from google.genai import errors, types

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

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _is_transient(exc: BaseException) -> bool:
    """True for Gemini errors worth retrying: any 5xx ``ServerError``, or a 429."""
    if isinstance(exc, errors.ServerError):
        return True
    if isinstance(exc, errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


class GeminiProvider:
    """An :class:`~lengua_core.llm.base.LLMProvider` backed by ``google-genai``."""

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        # Built lazily on first use (so construction does no I/O); injectable in tests.
        self._client = client

    @classmethod
    def from_env(cls) -> GeminiProvider:
        """Build the Gemini provider; the API key comes only from :func:`resolve_llm_key`.

        The key is obtained through the single key-resolution seam (task 3.9) — this class never
        reads the key env var itself — which fails fast with a clear error when it is unset. The
        model id still comes from ``GEMINI_MODEL`` (a non-secret).
        """
        api_key = resolve_llm_key(provider="gemini")
        return cls(api_key=api_key, model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))

    @property
    def model(self) -> str:
        """The Gemini model id this provider sends requests to."""
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

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
        contents = "Vocabulary words:\n" + "\n".join(f"- {w}" for w in capped)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction(
                language, vowelized=vowelized, level=level_band
            ),
            response_mime_type="application/json",
            response_schema=list[GeneratedCard],
            max_output_tokens=GENERATE_MAX_TOKENS,
        )

        def _call() -> list[GeneratedCard]:
            resp = self._get_client().models.generate_content(
                model=self._model, contents=contents, config=config
            )
            return list(resp.parsed or [])

        return call_with_retry(_call, is_transient=_is_transient)

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
        config = types.GenerateContentConfig(
            system_instruction=suggestion_instruction(
                language, level_band, known_words, count, topic
            ),
            response_mime_type="application/json",
            response_schema=list[str],
            max_output_tokens=SUGGEST_MAX_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        def _call() -> list[str]:
            resp = self._get_client().models.generate_content(
                model=self._model,
                contents=f"Suggest {count} new {language} vocabulary words.",
                config=config,
            )
            return list(resp.parsed or [])

        return call_with_retry(_call, is_transient=_is_transient)[:count]

    def explain_word(
        self, word: str, sentence: str, translation: str, language: str
    ) -> str:
        prompt = (
            f'In the {language} sentence: "{sentence}"\n'
            f'(English: "{translation}")\n\n'
            f'Briefly explain the word "{word}": its meaning and its role in this '
            f'sentence. Use at most two sentences. If it is a very simple or common '
            f'word (e.g. "to", "in", "and"), a single word or short phrase is enough.'
        )
        config = types.GenerateContentConfig(
            max_output_tokens=EXPLAIN_MAX_TOKENS,
            # Disable "thinking" so the small token budget isn't spent before any
            # answer text is produced (gemini-2.5-* think by default).
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        def _call() -> str:
            resp = self._get_client().models.generate_content(
                model=self._model, contents=prompt, config=config
            )
            return (resp.text or "").strip()

        text = call_with_retry(_call, is_transient=_is_transient)
        if not text:
            raise RuntimeError(
                "Gemini returned an empty explanation; please try again in a moment."
            )
        return text
