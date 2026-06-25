"""Discover service: suggest new vocabulary, then accept into the deck (task 1.3.6).

Two steps, mirroring the UX:

* :meth:`suggest` asks the provider for words at the learner's current CEFR band, excluding the
  vocabulary they already have saved cards for — a preview, nothing is persisted.
* :meth:`accept` feeds chosen words straight into the generate flow, so accepting suggestions
  produces real, saved cards.

It orchestrates the provider seam + repositories + the generate service, and emits no SQL itself.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core import proficiency
from lengua_core.llm.base import LLMProvider


class DiscoverService:
    """Suggest new words for a learner and turn accepted ones into cards."""

    def __init__(self, session: AsyncSession, provider: LLMProvider) -> None:
        self._provider = provider
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._proficiency = ProficiencyRepository(session)
        self._generate = GenerateService(session, provider)

    async def suggest(
        self,
        user_id: uuid.UUID,
        language_id: int,
        *,
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        """Return up to ``count`` new words for the learner (excludes already-known vocabulary).

        Raises :class:`NotFoundError` if the language is not the user's.
        """
        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        score = await self._proficiency.get_score(user_id, language_id)
        band: str = proficiency.band_for_score(score)
        known = await self._cards.known_words(user_id, language_id)
        suggestions: list[str] = self._provider.suggest_new_words(
            language.name, band, known, count=count, topic=topic
        )
        return suggestions

    async def accept(self, user_id: uuid.UUID, language_id: int, words: list[str]) -> list[Card]:
        """Generate and save cards for accepted ``words`` (delegates to the generate flow)."""
        built = await self._generate.generate(user_id, language_id, words)
        return await self._generate.save(user_id, language_id, built)
