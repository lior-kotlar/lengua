"""Integration tests for :class:`app.services.generate.GenerateService` (task 1.3.6).

The headline verify: run Generate -> Save with a stubbed provider (the deterministic
:class:`FakeLLM`) and the *real* repositories, then read the cards back. Also asserts the learner's
CEFR band is threaded into the provider call (FakeLLM echoes ``[language:band]`` into the
sentence), the unknown-language guard, and the empty-input edge.

That the service emits no SQL itself is enforced separately by the ``grep`` check in the task and
the Phase-1 exit gate.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core.llm.fake import FakeLLM
from lengua_core.models import GeneratedCard
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_generate_then_save_with_stub_provider(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Français", code="fr")
    service = GenerateService(db_session, FakeLLM())

    built = await service.generate(user_id, language.id, ["bonjour", "merci"])
    # Two words -> two sentences -> a recognition + production card each.
    assert len(built) == 4
    assert {card.direction for card in built} == {"recognition", "production"}
    # gen_level is tagged at the learner's current score (no proficiency row yet -> 0.0 / A1),
    # and FakeLLM echoes the language + band it was asked for into the sentence.
    assert all(card.gen_level == 0.0 for card in built)
    assert "[Français:A1]" in built[0].front

    saved = await service.save(user_id, language.id, built)
    assert len(saved) == 4
    assert all(card.saved for card in saved)
    assert all(card.fsrs_state is not None and card.due is not None for card in saved)

    # Read back through the real repository, scoped by user_id.
    rows = await CardsRepository(db_session).list_for_language(user_id, language.id)
    assert len(rows) == 4


async def test_generate_uses_overridden_band(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Español B2", code="es")
    service = GenerateService(db_session, FakeLLM())
    # Set a higher proficiency so the band the provider is asked for changes.
    await ProficiencyRepository(db_session).upsert(user_id, language.id, 3.4)  # floor 3 -> B2
    built = await service.generate(user_id, language.id, ["hola"])
    assert "[Español B2:B2]" in built[0].front
    assert all(card.gen_level == pytest.approx(3.4) for card in built)


async def test_generate_unknown_language_raises(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = GenerateService(db_session, FakeLLM())
    with pytest.raises(NotFoundError):
        await service.generate(user_id, 10**9, ["x"])
    with pytest.raises(NotFoundError):
        await service.save(user_id, 10**9, [])


async def test_generate_without_provider_raises(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    # The cards router constructs the service provider-less for save-only; generate must fail fast.
    user_id = uuid.UUID(demo_account.user_id)
    service = GenerateService(db_session)
    with pytest.raises(RuntimeError):
        await service.generate(user_id, 1, ["x"])


async def test_generate_and_save_empty(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Empty Lang", code="xx")
    service = GenerateService(db_session, FakeLLM())
    assert await service.generate(user_id, language.id, []) == []
    assert await service.save(user_id, language.id, []) == []


class _OverstatedCoverageProvider:
    """A provider whose ``used_words`` overstates coverage — drives the S7 coverage filter.

    Its one sentence genuinely uses only some requested words, yet labels ``used_words`` with a
    phantom word (``taza``, absent from the sentence), a word it used but the learner never
    requested (``bonita``), a case-/diacritic variant of a present requested word (``ESTA`` for
    ``está``), and a folded duplicate (``Casa``). Implements the full
    :class:`~lengua_core.llm.base.LLMProvider` Protocol so it type-checks where a provider is
    expected; only :meth:`generate_cards` is exercised.
    """

    name = "overstated"
    model = "overstated"

    def generate_cards(
        self,
        words: list[str],
        language: str,
        vowelized: bool = False,
        level_band: str | None = None,
    ) -> list[GeneratedCard]:
        return [
            GeneratedCard(
                sentence="Está la casa.",
                translation="The house is here.",
                used_words=["casa", "taza", "bonita", "ESTA", "Casa"],
            )
        ]

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def explain_word(self, word: str, sentence: str, translation: str, language: str) -> str:
        raise NotImplementedError


async def test_generate_filters_used_words_to_real_coverage(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    """S7: ``used_words`` is filtered to requested vocab that actually occurs in the sentence.

    The provider lists more words than its sentence supports; the service must keep only the words
    the learner asked for whose bare form really appears, case- and diacritic-insensitively, once
    each, preserving the original surface form. So the phantom ``taza`` and the never-requested
    ``bonita`` are dropped, ``ESTA`` (matching ``está``/``Está``) is kept, and the folded duplicate
    ``Casa`` collapses — both built directions carry ``["casa", "ESTA"]``.
    """
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Español", code="es")
    service = GenerateService(db_session, _OverstatedCoverageProvider())

    built = await service.generate(user_id, language.id, ["casa", "taza", "está"])

    assert len(built) == 2  # one sentence -> recognition + production
    assert {card.direction for card in built} == {"recognition", "production"}
    for card in built:
        assert card.used_words == ["casa", "ESTA"]
