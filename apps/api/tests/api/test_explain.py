"""Task 1.5.7 verify: ``POST /explain`` returns an explanation; a repeat is served from cache.

Seeds a production card (its ``back`` is the target sentence) with no cached notes, then calls
``POST /explain`` twice with identical args. The first call hits the provider and persists the
note into ``cards.word_explanations``; the second is served from that cache, so the provider's
call counter (FakeLLM's process-wide counter) advances exactly once.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.repositories.cards import CardsRepository
from lengua_core.llm.fake import FakeLLM
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SENTENCE = "El gato duerme en la silla."
_TRANSLATION = "The cat sleeps on the chair."


async def _seed_production_card(api_client: AsyncClient, db_session: AsyncSession) -> int:
    """A Spanish language + one production card for ``_SENTENCE`` with no cached explanations."""
    language_id = int(
        (await api_client.post("/languages", json={"name": "Spanish", "code": "es"})).json()["id"]
    )
    await CardsRepository(db_session).save_cards(
        DEV_USER_ID,
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
    return language_id


def _payload(language_id: int, word: str = "gato") -> dict[str, object]:
    return {
        "word": word,
        "sentence": _SENTENCE,
        "translation": _TRANSLATION,
        "language_id": language_id,
    }


async def test_explain_then_served_from_cache(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id = await _seed_production_card(api_client, db_session)
    FakeLLM.reset_call_count()

    # First call: cache miss -> provider invoked once -> note persisted.
    first = await api_client.post("/explain", json=_payload(language_id))
    assert first.status_code == 200
    body = first.json()
    assert body["word"] == "gato"
    explanation = body["explanation"]
    assert explanation  # non-empty
    assert FakeLLM.call_count == 1

    # Second identical call: cache hit -> same answer, provider NOT called again.
    second = await api_client.post("/explain", json=_payload(language_id))
    assert second.status_code == 200
    assert second.json()["explanation"] == explanation
    assert FakeLLM.call_count == 1

    # The explanation was persisted onto the card's word_explanations (keyed by bare word).
    cards = await CardsRepository(db_session).for_sentence(DEV_USER_ID, language_id, _SENTENCE)
    assert cards[0].word_explanations == {"gato": explanation}


async def test_explain_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.post("/explain", json=_payload(999999))
    assert resp.status_code == 404


async def test_explain_no_card_for_sentence_404(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id = await _seed_production_card(api_client, db_session)
    resp = await api_client.post(
        "/explain",
        json={
            "word": "perro",
            "sentence": "Una frase sin tarjeta.",
            "translation": "A sentence with no card.",
            "language_id": language_id,
        },
    )
    assert resp.status_code == 404


async def test_explain_punctuation_only_word_422(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id = await _seed_production_card(api_client, db_session)
    # min_length=1 passes "...", but it strips to empty -> service ValidationError -> 422.
    resp = await api_client.post("/explain", json=_payload(language_id, word="..."))
    assert resp.status_code == 422
