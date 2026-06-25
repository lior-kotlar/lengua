"""A deterministic, offline LLM stand-in.

:class:`FakeLLM` satisfies the :class:`~lengua_core.llm.base.LLMProvider` Protocol but performs
**no network or disk I/O and uses no randomness or clock** — every method is a pure function of
its arguments, so calling it twice with the same inputs returns equal output. This is what
unit, integration, and E2E tests run against (``LLM_PROVIDER=fake``) so CI never burns real
Groq/Gemini quota and the results are reproducible.

It also keeps a process-wide :attr:`FakeLLM.call_count` so an E2E test can assert the LLM seam
was exercised the expected number of times (and, with a real provider swapped in behind an
egress block, that *zero* real calls were made). The counter is observational only — it never
changes the returned values.
"""

from __future__ import annotations

from lengua_core.models import GeneratedCard, WordNote

# Trivial function words get a short gloss rather than a full sentence, matching the real
# provider's behaviour (see ``gemini.explain_word``).
_TRIVIAL_WORDS = frozenset(
    {"to", "in", "and", "a", "the", "of", "is", "it", "on", "at", "an"}
)

# A small fixed pool of plausible vocabulary used to answer ``suggest_new_words`` without a
# model. Words already known are filtered out; the order is stable.
_SUGGESTION_POOL = (
    "house",
    "water",
    "friend",
    "morning",
    "book",
    "city",
    "music",
    "bread",
    "river",
    "window",
    "garden",
    "letter",
)


class FakeLLM:
    """Deterministic, network-free implementation of :class:`LLMProvider`."""

    #: Process-wide count of provider calls across all instances. Tests may reset it via
    #: :meth:`reset_call_count` and read it to assert the seam was (or was not) exercised.
    call_count: int = 0

    @classmethod
    def reset_call_count(cls) -> None:
        """Zero the shared call counter (call from a test fixture before asserting)."""
        cls.call_count = 0

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        type(self).call_count += 1
        cleaned = [w.strip() for w in words if w.strip()]
        if not cleaned:
            return []

        cards: list[GeneratedCard] = []
        for word in cleaned:
            # A fully deterministic sentence: the word echoed back in a fixed template. The
            # band/vowelized flags are reflected so callers can see they were threaded through,
            # without introducing any nondeterminism.
            suffix = " (vowelized)" if vowelized else ""
            band = level_band or "A1"
            sentence = f"[{language}:{band}] This is a sentence with {word}.{suffix}"
            translation = f"This is a sentence with {word}."
            cards.append(
                GeneratedCard(
                    sentence=sentence,
                    translation=translation,
                    used_words=[word],
                    word_notes=[
                        WordNote(word=word, note=self._note_for(word)),
                    ],
                )
            )
        return cards

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        type(self).call_count += 1
        known = {w.strip().lower() for w in known_words}
        # Deterministic selection: walk the fixed pool in order, skipping known words.
        suggestions = [w for w in _SUGGESTION_POOL if w.lower() not in known]
        return suggestions[: max(count, 0)]

    def explain_word(
        self, word: str, sentence: str, translation: str, language: str
    ) -> str:
        type(self).call_count += 1
        return self._note_for(word)

    @staticmethod
    def _note_for(word: str) -> str:
        """A deterministic gloss for ``word`` — short for trivial function words."""
        bare = word.strip().lower()
        if bare in _TRIVIAL_WORDS:
            return bare
        return f"{word}: a {len(word.strip())}-letter word used in this sentence."
