"""Integration tests for the reviews + proficiency repositories (task 1.3.4).

The verify: grading a card writes a ``reviews`` row and an *upserted* ``proficiency`` row for that
user. Here we exercise the two repositories directly (the full grade orchestration is covered in
``tests/services/test_review_service.py``): insert a review, then upsert proficiency twice and
assert it stays a single row reflecting the latest value — all scoped by ``user_id``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Proficiency, Review
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.reviews import ReviewsRepository
from scripts.seed_e2e import SeedResult
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_insert_review_and_upsert_proficiency(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Polski", code="pl")
    due = datetime(2026, 1, 1, tzinfo=UTC)
    saved = await CardsRepository(db_session).save_cards(
        user_id, language.id, [make_new_card(fsrs_state={"due": due.isoformat()}, due=due)]
    )
    card = saved[0]

    # Insert a review row.
    review = await ReviewsRepository(db_session).add(user_id, card.id, rating=3)
    assert review.id is not None
    review_count = await db_session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.user_id == user_id, Review.card_id == card.id)
    )
    assert review_count == 1

    # Upsert proficiency: insert, then update — one row, latest value wins.
    prof = ProficiencyRepository(db_session)
    await prof.upsert(user_id, language.id, 1.0)
    assert await prof.get_score(user_id, language.id) == pytest.approx(1.0)
    await prof.upsert(user_id, language.id, 2.5)
    assert await prof.get_score(user_id, language.id) == pytest.approx(2.5)

    prof_count = await db_session.scalar(
        select(func.count())
        .select_from(Proficiency)
        .where(Proficiency.user_id == user_id, Proficiency.language_id == language.id)
    )
    assert prof_count == 1

    # Unrecorded (user, language) defaults to the CEFR floor.
    assert await prof.get_score(user_id, 10**9) == 0.0
