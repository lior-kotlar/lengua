"""Task 1.5.5 verify: grade a due card -> due moves forward + a reviews row + proficiency change.

Walks generate -> save -> ``GET /review/due`` -> ``POST /review/{id}/grade`` over HTTP, then
asserts the FSRS reschedule, the persisted review row, and the proficiency nudge.
"""

from __future__ import annotations

from datetime import datetime

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
