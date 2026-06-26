"""Discover service: suggest new vocabulary, then accept into the deck (task 1.3.6).

Two steps, mirroring the UX:

* :meth:`suggest` asks the provider for words at the learner's current CEFR band, excluding the
  vocabulary they already have saved cards for — a preview, nothing is persisted.
* :meth:`accept` feeds chosen words straight into the generate flow, so accepting suggestions
  produces real, saved cards.

It orchestrates the provider seam + repositories + the generate service, and emits no SQL itself.

**Cost guard (Phase 3.4 — count the billed call even if persistence fails).** ``accept`` makes a
real (billed) provider call and *then* persists. If the persist failed after the provider already
ran, a post-persist increment would skip — a billed call that bumped neither the global
``llm_budget`` nor the per-user ``llm_usage`` (and so dodged the cap/kill-switch). So, mirroring
``ExplainService``, when a :class:`~app.quota.QuotaGuard` is supplied (the request path always
passes one) ``accept`` records the spend **immediately after the successful provider call and before
``save``**. A ``save`` failure then still counts the call (the safe direction for a "never get a
bill" guard) and rolls the cards back; the increment commits on its own privileged usage session.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core import proficiency
from lengua_core.llm.base import LLMProvider

if TYPE_CHECKING:
    # Imported only for the type annotation. A runtime import would form a cycle: this module is
    # eagerly pulled in by ``app.services.__init__`` (which ``app.deps`` triggers), while
    # ``app.quota`` imports ``app.deps`` — so importing it here at runtime catches it half-built.
    # ``from __future__ import annotations`` keeps the ``QuotaGuard`` annotation a string, so the
    # TYPE_CHECKING-only import is enough (mirrors how ``ExplainService`` only works because the
    # explain router imports it lazily, after ``app.quota`` has finished loading).
    from app.quota import QuotaGuard


class DiscoverService:
    """Suggest new words for a learner and turn accepted ones into cards."""

    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider,
        limiter: LLMConcurrencyLimiter | None = None,
    ) -> None:
        self._provider = provider
        # Bound provider calls under the global concurrency cap (task 3.5.1); default to the
        # singleton and thread the same limiter into the generate flow ``accept`` delegates to.
        self._limiter = limiter if limiter is not None else get_llm_limiter()
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._proficiency = ProficiencyRepository(session)
        self._generate = GenerateService(session, provider, self._limiter)

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
        # Blocking provider call under the global concurrency cap (task 3.5.1).
        suggestions: list[str] = await self._limiter.run(
            self._provider.suggest_new_words,
            language.name,
            band,
            known,
            count=count,
            topic=topic,
        )
        return suggestions

    async def accept(
        self,
        user_id: uuid.UUID,
        language_id: int,
        words: list[str],
        guard: QuotaGuard | None = None,
    ) -> list[Card]:
        """Generate and save cards for accepted ``words`` (delegates to the generate flow).

        The provider runs inside :meth:`GenerateService.generate`; when a ``guard`` is supplied the
        spend is counted **right after** that successful provider call and **before** :meth:`save`,
        so a persistence failure still bills the (already-made) provider call rather than leaving a
        real call uncounted — the safe direction for the global kill-switch.
        """
        built = await self._generate.generate(user_id, language_id, words)
        if guard is not None:
            await guard.record_success()
        return await self._generate.save(user_id, language_id, built)
