"""Tap-a-word explanation service (task 1.5.7).

When a learner taps a word in a card's sentence, this returns a short explanation of that word —
served from the card's cached ``word_explanations`` when available, otherwise fetched from the
LLM provider once and persisted there. There is **no** ``word_explanations`` table: the schema
carries a ``cards.word_explanations`` JSONB column (a ``{bare_word: note}`` map), so the cache
lives on the production card that renders the sentence — matching the legacy Streamlit behaviour.

It orchestrates the provider seam + repositories and emits no SQL itself.

**Cost guard (Phase 3.2 — cache-aware).** ``/explain`` is the one LLM endpoint with a cache, so the
daily-cap gate cannot be a pure route dependency (that would gate+count even a free cache hit).
Instead the router hands in an unchecked :class:`~app.quota.QuotaGuard` and this service runs the
gate **only on a cache miss**: it checks the cap *after* the cache lookup and increments the
counter *after* a successful provider call. A cache hit therefore makes no provider call, passes no
gate, and bumps no counter — it is free.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.quota import QuotaGuard
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.services.errors import NotFoundError, ValidationError
from lengua_core.cards import bare_word
from lengua_core.llm.base import LLMProvider


class ExplainService:
    """Explain a tapped word, caching the result on the card's ``word_explanations``."""

    def __init__(self, session: AsyncSession, provider: LLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)

    async def explain(
        self,
        user_id: uuid.UUID,
        language_id: int,
        word: str,
        sentence: str,
        translation: str,
        guard: QuotaGuard | None = None,
    ) -> str:
        """Return ``word``'s explanation for ``sentence`` (cache-first, then provider + persist).

        Raises :class:`ValidationError` for an empty word, and :class:`NotFoundError` if the
        language is not the user's or no card of theirs renders ``sentence``. When a ``guard`` is
        supplied (the request path always passes one), the per-user daily ``explain`` cap is
        enforced on a cache **miss** only, and counted after the provider call succeeds.
        """
        bare = bare_word(word)
        if not bare:
            raise ValidationError("Word must not be empty.")

        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        cards = await self._cards.for_sentence(user_id, language_id, sentence)
        if not cards:
            raise NotFoundError("No card found for that sentence.")

        # Cache hit: any matching card that already has this word's note — free (no gate, no count).
        for card in cards:
            cached = (card.word_explanations or {}).get(bare)
            if cached is not None:
                return str(cached)

        # Cache miss: this WILL call the provider, so gate the per-user daily cap first (429 if the
        # user is at their cap). Then ask the provider once, count the successful spend, and persist
        # the note onto every matching card so a later tap (on either copy of the sentence) is
        # served from cache. The explicit annotation narrows the provider's result (Any across the
        # pure-core import boundary) to ``str``.
        if guard is not None:
            await guard.check()
        note: str = self._provider.explain_word(word, sentence, translation, language.name)
        if guard is not None:
            await guard.record_success()
        for card in cards:
            await self._cards.set_explanation(card, bare, note)
        await self._session.commit()
        return note
