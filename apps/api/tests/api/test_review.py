"""Task 1.5.5 verify: grade a due card -> due moves forward + a reviews row + proficiency change.

Walks generate -> save -> ``GET /review/due`` -> ``POST /review/{id}/grade`` over HTTP, then
asserts the FSRS reschedule, the persisted review row, and the proficiency nudge. Also (task 4.8b)
proves ``GET /review/due`` honors the user's per-user ``daily_new_limit`` / ``daily_total_limit``
settings end-to-end (and falls back to the config defaults when they are unset/invalid).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Review
from app.deps import DEV_USER_ID
from app.repositories.cards import CardsRepository
from app.repositories.proficiency import ProficiencyRepository
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A past instant so freshly-seeded cards are due now; the bare ``{"due": ...}`` FSRS state has no
# ``last_review``, so the scheduler classifies these as never-reviewed (``new``) cards.
_PAST = datetime(2025, 1, 1, tzinfo=UTC)
_NEW_STATE = {"due": _PAST.isoformat()}


async def _seed_new_cards(db_session: AsyncSession, language_id: int, count: int) -> None:
    """Persist ``count`` saved, due-now, never-reviewed cards for the dev user."""
    await CardsRepository(db_session).save_cards(
        DEV_USER_ID,
        language_id,
        [make_new_card(saved=True, fsrs_state=_NEW_STATE, due=_PAST) for _ in range(count)],
    )
    await db_session.flush()


async def _save_one_word(api_client: AsyncClient, language_id: int) -> None:
    previews = (
        await api_client.post("/generate", json={"language_id": language_id, "words": ["hola"]})
    ).json()
    saved = await api_client.post(
        "/cards/save", json={"language_id": language_id, "cards": previews}
    )
    assert saved.status_code == 200


async def test_due_split_then_grade(api_client: AsyncClient, db_session: AsyncSession) -> None:
    language_id = int(
        (await api_client.post("/languages", json={"name": "Spanish", "code": "es"})).json()["id"]
    )
    await _save_one_word(api_client, language_id)

    # GET /review/due -> the freshly-saved cards are due *and* new (never reviewed).
    due_resp = await api_client.get("/review/due", params={"language_id": language_id})
    assert due_resp.status_code == 200
    batch = due_resp.json()
    assert len(batch["new"]) == 2  # recognition + production
    assert batch["due"] == []

    target = batch["new"][0]
    old_due = datetime.fromisoformat(target["due"])

    # POST grade (Easy) -> rescheduled forward.
    graded = await api_client.post(f"/review/{target['id']}/grade", json={"rating": 4})
    assert graded.status_code == 200
    result = graded.json()
    assert result["card_id"] == target["id"]
    assert datetime.fromisoformat(result["due"]) > old_due
    assert result["score_changed"] is True
    assert result["score"] > 0.0

    # A reviews row was written for this card.
    review_count = await db_session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.user_id == DEV_USER_ID, Review.card_id == target["id"])
    )
    assert review_count == 1

    # Proficiency was nudged above the A1 floor.
    assert await ProficiencyRepository(db_session).get_score(DEV_USER_ID, language_id) > 0.0


async def test_grade_out_of_range_rating_422(api_client: AsyncClient) -> None:
    # Pydantic ge/le bounds reject 0 and 9 before the service is reached.
    assert (await api_client.post("/review/1/grade", json={"rating": 9})).status_code == 422
    assert (await api_client.post("/review/1/grade", json={"rating": 0})).status_code == 422


async def test_grade_unknown_card_404(api_client: AsyncClient) -> None:
    assert (await api_client.post("/review/999999/grade", json={"rating": 3})).status_code == 404


async def test_grade_card_without_fsrs_state_422(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id = int(
        (await api_client.post("/languages", json={"name": "Spanish", "code": "es"})).json()["id"]
    )
    # A card not in the deck (no FSRS state) is owned but ungradeable -> service ValidationError.
    saved = await CardsRepository(db_session).save_cards(
        DEV_USER_ID, language_id, [make_new_card(saved=False, fsrs_state=None, due=None)]
    )
    resp = await api_client.post(f"/review/{saved[0].id}/grade", json={"rating": 3})
    assert resp.status_code == 422


async def _new_count(api_client: AsyncClient, language_id: int) -> int:
    """The number of ``new`` cards ``GET /review/due`` returns for ``language_id`` right now."""
    resp = await api_client.get("/review/due", params={"language_id": language_id})
    assert resp.status_code == 200
    return len(resp.json()["new"])


async def test_review_due_honors_user_daily_new_limit(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Task 4.8b: a per-user ``daily_new_limit`` actually bounds the new cards in the due batch.

    Seeds more brand-new cards than the limit, then proves the limit caps the batch — and that a
    blank/invalid value falls back to the ``lengua_core`` config default (so all are returned).
    """
    language_id = int(
        (await api_client.post("/languages", json={"name": "Italiano", "code": "it"})).json()["id"]
    )
    await _seed_new_cards(db_session, language_id, count=5)

    # No setting yet -> the config default (10) applies, so all 5 new cards come back.
    assert await _new_count(api_client, language_id) == 5

    # Set daily_new_limit=2 -> the batch is now limited to exactly 2 new cards.
    put = await api_client.put("/settings", json={"values": {"daily_new_limit": "2"}})
    assert put.status_code == 200
    assert await _new_count(api_client, language_id) == 2

    # A blank value is treated as unset -> falls back to the default again (all 5).
    await api_client.put("/settings", json={"values": {"daily_new_limit": "   "}})
    assert await _new_count(api_client, language_id) == 5

    # A non-numeric value also falls back to the default (never a 500).
    await api_client.put("/settings", json={"values": {"daily_new_limit": "lots"}})
    assert await _new_count(api_client, language_id) == 5


async def test_review_due_honors_user_daily_total_limit(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Task 4.8b: a per-user ``daily_total_limit`` caps the merged (new + due) batch."""
    language_id = int(
        (await api_client.post("/languages", json={"name": "Polski", "code": "pl"})).json()["id"]
    )
    await _seed_new_cards(db_session, language_id, count=4)

    # daily_new_limit is unset (default 10), so without a total cap all 4 are returned.
    assert await _new_count(api_client, language_id) == 4

    # daily_total_limit=3 caps the merged batch to 3 cards total.
    put = await api_client.put("/settings", json={"values": {"daily_total_limit": "3"}})
    assert put.status_code == 200
    batch = (await api_client.get("/review/due", params={"language_id": language_id})).json()
    assert len(batch["new"]) + len(batch["due"]) == 3
