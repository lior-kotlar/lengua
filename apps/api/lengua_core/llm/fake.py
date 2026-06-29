"""Deterministic, offline LLM provider for unit/integration/E2E tests.

Returns canned :class:`GeneratedCard` / :class:`WordNote` output derived purely from the
inputs — identical across repeated calls, no network, no nondeterminism. This lets tests
assert *app* behavior rather than a model's wording, and never burns real provider quota.
"""

from lengua_core.models import GeneratedCard, WordNote


class FakeLLM:
    """A stand-in :class:`~lengua_core.llm.base.LLMProvider` with stable, fabricated output."""

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        cleaned = [w.strip() for w in words if w.strip()]
        marker = f"{language}+vowels" if vowelized else language
        return [
            GeneratedCard(
                sentence=f"[{marker}] A simple sentence with {word}.",
                translation=f"A simple sentence with {word}.",
                used_words=[word],
                word_notes=[WordNote(word=word, note=f"{word}: a {language} vocabulary word.")],
            )
            for word in cleaned
        ]

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        known = {w.strip() for w in known_words}
        prefix = (topic or language).strip().lower().replace(" ", "-")
        suggestions: list[str] = []
        index = 1
        while len(suggestions) < count:
            candidate = f"{prefix}-{level_band.lower()}-word-{index}"
            if candidate not in known:
                suggestions.append(candidate)
            index += 1
        return suggestions

    def explain_word(
        self,
        word: str,
        sentence: str,
        translation: str,
        language: str,
    ) -> str:
        return f'"{word}" ({language}): its dictionary sense, as used in this sentence.'
