"""Generate -> Save service (task 1.3.6).

This is the heart of the loop: turn vocabulary words into example sentences (via the configured
LLM provider) and persist them as flashcards. It orchestrates the *pure* ``lengua_core`` logic
(prompt-level/band selection, card building, fresh FSRS state) and the repositories, and emits no
SQL itself:

* :meth:`generate` looks up the language + the learner's current CEFR band, asks the provider for
  sentences, and builds the recognition + production card pair for each — returning the unsaved
  pair (each tagged with the ``gen_level`` it was generated at) so a router can preview them.
* :meth:`save` persists those built cards into the deck, giving each its own fresh FSRS state so
  the two directions schedule independently, then commits.

The provider is injected (the :class:`~lengua_core.llm.base.LLMProvider` seam), so tests pass a
deterministic stub and never touch the network.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.repositories.cards import CardsRepository, NewCard
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from lengua_core import cards as core_cards
from lengua_core import proficiency, scheduler
from lengua_core.cards import BuiltCard
from lengua_core.llm.base import LLMProvider


class GenerateService:
    """Generate example-sentence card pairs and save them to a user's deck."""

    def __init__(self, session: AsyncSession, provider: LLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._proficiency = ProficiencyRepository(session)

    async def generate(
        self, user_id: uuid.UUID, language_id: int, words: list[str]
    ) -> list[BuiltCard]:
        """Generate the recognition + production card pairs for ``words`` (unsaved).

        Raises :class:`NotFoundError` if the language is not the user's. The cards are tagged with
        the learner's current continuous score (``gen_level``) so later reviews only move the
        level for current-level material.
        """
        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        score = await self._proficiency.get_score(user_id, language_id)
        band: str = proficiency.band_for_score(score)
        cleaned = [w.strip() for w in words if w.strip()]

        generated = self._provider.generate_cards(
            cleaned, language.name, vowelized=language.vowelized, level_band=band
        )
        built: list[BuiltCard] = []
        for card in generated:
            built.extend(core_cards.build_cards(card, gen_level=score))
        return built

    async def save(
        self, user_id: uuid.UUID, language_id: int, built: list[BuiltCard]
    ) -> list[Card]:
        """Persist built card pairs into the user's deck (``saved``, due now) and commit.

        Raises :class:`NotFoundError` if the language is not the user's.
        """
        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        rows: list[NewCard] = []
        for card in built:
            # Each card gets its own fresh FSRS state so the two directions schedule apart.
            state: tuple[str, str] = scheduler.new_card_state()
            fsrs_json, due_iso = state
            fsrs_state: dict[str, Any] = json.loads(fsrs_json)
            rows.append(
                NewCard(
                    front=card.front,
                    back=card.back,
                    direction=card.direction,
                    used_words=card.used_words,
                    word_explanations=card.word_explanations,
                    gen_level=card.gen_level,
                    saved=True,
                    fsrs_state=fsrs_state,
                    due=datetime.fromisoformat(due_iso),
                )
            )

        saved = await self._cards.save_cards(user_id, language_id, rows)
        await self._session.commit()
        return saved
