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

import threading
from collections.abc import Iterable

from lengua_core.models import GeneratedCard, WordNote

from .usage import report_usage

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


def _stub_tokens(texts: Iterable[str]) -> int:
    """A deterministic, positive-ish token-count stub: the whitespace-word count across ``texts``.

    A pure function of the text (no clock/RNG), so a repeated identical call reports identical
    counts — matching ``FakeLLM``'s "same input → same output" contract. Used only to populate the
    observability span's ``llm.tokens_in/out`` for the fake provider.
    """
    return sum(len(text.split()) for text in texts)


class FakeLLM:
    """Deterministic, network-free implementation of :class:`LLMProvider`."""

    #: Identity surfaced on the per-call observability span (``llm.provider`` / ``llm.model``), so a
    #: fake call still carries a provider + model attribute (task 3.8.1).
    name = "fake"
    model = "fake"

    #: Process-wide count of provider calls across all instances. Tests may reset it via
    #: :meth:`reset_call_count` and read it to assert the seam was (or was not) exercised.
    call_count: int = 0

    #: Guards :attr:`call_count` so increments stay atomic when calls run concurrently in worker
    #: threads (``asyncio.to_thread`` under the concurrency cap) — without it the read-modify-write
    #: ``+= 1`` can lose updates, making the "operator key invoked ≤ budget" load-test count flaky.
    _count_lock = threading.Lock()

    @classmethod
    def reset_call_count(cls) -> None:
        """Zero the shared call counter (call from a test fixture before asserting)."""
        with cls._count_lock:
            cls.call_count = 0

    @classmethod
    def _bump_call_count(cls) -> None:
        """Atomically increment the shared :attr:`call_count` (thread-safe under the concurrency cap)."""
        with cls._count_lock:
            cls.call_count += 1

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        type(self)._bump_call_count()
        cleaned = [w.strip() for w in words if w.strip()]
        if not cleaned:
            report_usage(0, 0)
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
        # Deterministic stub token counts (a pure function of input/output text) so the per-call
        # observability span always carries ``llm.tokens_in/out`` even for the fake provider.
        report_usage(_stub_tokens(cleaned), _stub_tokens(c.sentence for c in cards))
        return cards

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        type(self)._bump_call_count()
        known = {w.strip().lower() for w in known_words}
        # Deterministic selection: walk the fixed pool in order, skipping known words.
        suggestions = [w for w in _SUGGESTION_POOL if w.lower() not in known][: max(count, 0)]
        report_usage(_stub_tokens(known_words), _stub_tokens(suggestions))
        return suggestions

    def explain_word(
        self, word: str, sentence: str, translation: str, language: str
    ) -> str:
        type(self)._bump_call_count()
        note = self._note_for(word)
        report_usage(_stub_tokens([word, sentence, translation]), _stub_tokens([note]))
        return note

    @staticmethod
    def _note_for(word: str) -> str:
        """A deterministic gloss for ``word`` — short for trivial function words."""
        bare = word.strip().lower()
        if bare in _TRIVIAL_WORDS:
            return bare
        return f"{word}: a {len(word.strip())}-letter word used in this sentence."
