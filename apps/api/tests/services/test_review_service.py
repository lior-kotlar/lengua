"""Integration tests for :class:`app.services.review.ReviewService` (task 1.3.6).

Covers the two review responsibilities:

* :meth:`grade` — applying an FSRS rating reschedules the card forward, writes a ``reviews`` row,
  and nudges proficiency (all in one transaction), plus the not-found / bad-rating guards.
* :meth:`due_batch` — the scheduler's new-vs-reviewed split is respected and capped by the limits.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Review
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError, ValidationError
from app.services.generate import GenerateService
from app.services.review import ReviewService
from lengua_core.llm.fake import FakeLLM
from lengua_core.scheduler import new_card_state
from scripts.seed_e2e import SeedResult
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A past instant so freshly-built cards are due; older still for the "last_review" stamp.
PAST = datetime(2025, 1, 1, tzinfo=UTC)
_NEW_STATE = {"due": PAST.isoformat()}
_REVIEWED_STATE = {"due": PAST.isoformat(), "last_review": "2024-12-01T00:00:00+00:00"}


async def test_grade_reschedules_logs_and_nudges(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Deutsch", code="de")
    generate = GenerateService(db_session, FakeLLM())
    saved = await generate.save(
        user_id, language.id, await generate.generate(user_id, language.id, ["haus"])
    )
    card = saved[0]
    old_due = card.due
    assert old_due is not None

    result = await ReviewService(db_session).grade(user_id, card.id, rating=4)  # Easy
    assert result.due > old_due  # rescheduled forward
    assert result.score_changed is True
    assert result.score > 0.0

    review_count = await db_session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.user_id == user_id, Review.card_id == card.id)
    )
    assert review_count == 1
    assert await ProficiencyRepository(db_session).get_score(user_id, language.id) > 0.0


async def test_grade_below_level_card_does_not_move_proficiency(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Esperanto", code="eo")
    # A real FSRS state (so the card is gradeable) but a gen_level far from the current score (0.0),
    # so register_review leaves the level untouched.
    fsrs_json, due_iso = new_card_state()
    saved = await CardsRepository(db_session).save_cards(
        user_id,
        language.id,
        [
            make_new_card(
                fsrs_state=json.loads(fsrs_json), due=datetime.fromisoformat(due_iso), gen_level=5.0
            )
        ],
    )

    result = await ReviewService(db_session).grade(user_id, saved[0].id, rating=3)
    assert result.score_changed is False
    assert result.score == 0.0
    # No proficiency row was written.
    assert await ProficiencyRepository(db_session).get_score(user_id, language.id) == 0.0


async def test_grade_guards(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Café", code="xz")
    review = ReviewService(db_session)

    # Unknown card.
    with pytest.raises(NotFoundError):
        await review.grade(user_id, 10**9, rating=3)

    # Out-of-range rating.
    with pytest.raises(ValidationError):
        await review.grade(user_id, 10**9, rating=9)

    # Card with no FSRS state cannot be graded.
    saved = await CardsRepository(db_session).save_cards(
        user_id, language.id, [make_new_card(saved=False, fsrs_state=None, due=None)]
    )
    with pytest.raises(ValidationError):
        await review.grade(user_id, saved[0].id, rating=3)


async def test_due_batch_respects_new_and_total_limits(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Latine", code="la")
    cards = CardsRepository(db_session)
    # 3 brand-new (never reviewed) + 2 reviewed cards, all due in the past.
    await cards.save_cards(
        user_id,
        language.id,
        [make_new_card(fsrs_state=_NEW_STATE, due=PAST) for _ in range(3)]
        + [make_new_card(fsrs_state=_REVIEWED_STATE, due=PAST) for _ in range(2)],
    )
    review = ReviewService(db_session)

    # Reviewed cards aren't limited by new_limit; new cards are.
    assert len(await review.due_batch(user_id, language.id, new_limit=0, total_limit=50)) == 2
    assert len(await review.due_batch(user_id, language.id, new_limit=1, total_limit=50)) == 3
    # total_limit caps the merged batch (2 reviewed + 3 new = 5 -> 4).
    assert len(await review.due_batch(user_id, language.id, new_limit=10, total_limit=4)) == 4
    # Everything is due with generous defaults.
    assert len(await review.due_batch(user_id, language.id)) == 5
