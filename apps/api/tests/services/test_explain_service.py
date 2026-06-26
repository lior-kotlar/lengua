"""Integration tests for :class:`app.services.explain.ExplainService` (tasks 1.5.7 / 3.2.4).

Exercises the service directly (no HTTP) to cover the cache-aware behaviour at the unit boundary:

* a cache **miss** calls the provider once and persists the note onto the matching card;
* a later identical call is a cache **hit** — same answer, no second provider call;
* the daily-cap ``guard`` is **optional** — with ``guard=None`` (the default) the service still
  works and runs no gate/increment (the HTTP layer always supplies a guard; this proves the seam
  is decoupled from FastAPI).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.services.explain import ExplainService
from lengua_core.llm.fake import FakeLLM
from scripts.seed_e2e import SeedResult
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SENTENCE = "El gato duerme en la silla."
_TRANSLATION = "The cat sleeps on the chair."


async def _seed_card(db_session: AsyncSession, user_id: uuid.UUID, language_id: int) -> None:
    await CardsRepository(db_session).save_cards(
        user_id,
        language_id,
        [
            make_new_card(
                direction="production",
                front=_TRANSLATION,
                back=_SENTENCE,
                used_words=["gato", "silla"],
                word_explanations=None,
            )
        ],
    )


async def test_explain_without_guard_caches(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    """With ``guard=None`` the service gates nothing: a miss calls the provider, a hit does not."""
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Portuguese", code="pt")
    await _seed_card(db_session, user_id, language.id)
    service = ExplainService(db_session, FakeLLM())
    FakeLLM.reset_call_count()

    # Cache miss: provider called once, note returned (guard omitted → no gate, no increment).
    note = await service.explain(user_id, language.id, "gato", _SENTENCE, _TRANSLATION)
    assert note
    assert FakeLLM.call_count == 1

    # Cache hit: same answer, provider not called again.
    again = await service.explain(user_id, language.id, "gato", _SENTENCE, _TRANSLATION)
    assert again == note
    assert FakeLLM.call_count == 1

    # The note was persisted onto the card's word_explanations (keyed by bare word).
    cards = await CardsRepository(db_session).for_sentence(user_id, language.id, _SENTENCE)
    assert cards[0].word_explanations == {"gato": note}
