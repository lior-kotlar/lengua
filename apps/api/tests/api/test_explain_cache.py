"""Task 3.6.2 verify: an ``/explain`` cache hit skips the LLM **and** the usage counter.

A second ``/explain`` for the same word+language returns the persisted explanation (from
``cards.word_explanations``, Phase 1.5b) with **zero** provider calls (``FakeLLM.call_count``
unchanged) **and no ``llm_usage`` increment** — only the first (cache-miss) call spends the operator
key and is counted. This is the authoritative "cache hit is free" proof for the cost guard:

* ``tests/api/test_explain.py`` already proves the *persistence shape* (the note lands in
  ``word_explanations``) and that the provider is called once; and
* ``tests/api/test_quota_endpoints.py`` proves a cache hit stays free even when the cap is spent.

This test adds the dimension neither covers explicitly: the per-user ``llm_usage`` counter does not
move on the cache hit (so the hit consumes no cap / budget).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.repositories.cards import CardsRepository
from app.repositories.usage import UsageRepository
from lengua_core.llm.fake import FakeLLM
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SENTENCE = "La niña lee un libro."
_TRANSLATION = "The girl reads a book."


async def _seed_card(api_client: AsyncClient, db_session: AsyncSession) -> int:
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
                used_words=["niña", "libro"],
                word_explanations=None,
            )
        ],
    )
    return language_id


def _payload(language_id: int, word: str = "libro") -> dict[str, object]:
    return {
        "word": word,
        "sentence": _SENTENCE,
        "translation": _TRANSLATION,
        "language_id": language_id,
    }


async def test_cache_hit_skips_llm(api_client: AsyncClient, db_session: AsyncSession) -> None:
    language_id = await _seed_card(api_client, db_session)
    day = datetime.now(UTC).date()
    usage = UsageRepository(db_session)
    FakeLLM.reset_call_count()

    # First call: cache miss → provider invoked once → llm_usage(explain) incremented to 1.
    first = await api_client.post("/explain", json=_payload(language_id))
    assert first.status_code == 200
    explanation = first.json()["explanation"]
    assert explanation  # non-empty
    assert FakeLLM.call_count == 1
    assert await usage.get_user_daily_count(DEV_USER_ID, "explain", day) == 1

    # Second identical call: cache hit → same answer, ZERO provider calls, NO further increment.
    second = await api_client.post("/explain", json=_payload(language_id))
    assert second.status_code == 200
    assert second.json()["explanation"] == explanation
    assert FakeLLM.call_count == 1  # unchanged — the LLM was not called again
    assert await usage.get_user_daily_count(DEV_USER_ID, "explain", day) == 1  # unchanged
