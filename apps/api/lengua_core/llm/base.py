"""The provider-agnostic LLM interface.

Mirrors the three call signatures from the legacy ``lengua/gemini.py`` so any provider
(Groq, Gemini, or the test fake) is interchangeable behind the same contract.
"""

from typing import Protocol, runtime_checkable

from lengua_core.models import GeneratedCard


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface every LLM provider implements."""

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        """Generate example sentences in ``language`` using the given vocabulary words."""
        ...

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        """Pick ``count`` new words at ``level_band`` the learner doesn't already know."""
        ...

    def explain_word(
        self,
        word: str,
        sentence: str,
        translation: str,
        language: str,
    ) -> str:
        """Return a short explanation of ``word``'s meaning and role in ``sentence``."""
        ...
