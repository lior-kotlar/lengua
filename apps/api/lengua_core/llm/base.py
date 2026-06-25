"""The provider-agnostic LLM interface.

:class:`LLMProvider` is a :class:`typing.Protocol` (structural typing) so a provider does not
need to subclass anything — any object exposing these three methods satisfies it. The method
signatures mirror today's ``lengua_core.gemini`` functions so a real provider is a drop-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lengua_core.models import GeneratedCard


@runtime_checkable
class LLMProvider(Protocol):
    """Everything the app needs from an LLM, independent of the concrete vendor."""

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        """Generate example sentences in ``language`` using the given vocabulary ``words``.

        Returns one :class:`GeneratedCard` per sentence. An empty ``words`` list yields ``[]``.
        """
        ...

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        """Suggest ``count`` new vocabulary words the learner does not already know.

        ``known_words`` are excluded; ``level_band`` is a CEFR band (e.g. ``"A2"``) and
        ``topic`` optionally biases the theme.
        """
        ...

    def explain_word(
        self, word: str, sentence: str, translation: str, language: str
    ) -> str:
        """Return a short (≤ 2 sentence) explanation of ``word``'s meaning and role."""
        ...
