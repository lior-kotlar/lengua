"""Review service: due-batch selection and grading (task 1.3.6).

Orchestrates the *pure* FSRS scheduler and proficiency math (``lengua_core``) with the card,
review, and proficiency repositories — emitting no SQL itself:

* :meth:`due_batch` pulls the user's saved/due cards and lets ``scheduler.select_due_batch`` pick
  the batch (new cards limited separately so a big import doesn't bury reviews).
* :meth:`grade` applies an FSRS rating to one card — rescheduling it, logging the review, and
  nudging the language's proficiency — all in a single committed transaction so the three writes
  stay atomic.

``lengua_core.scheduler`` works on a card's FSRS state as a JSON *string* (its portable form),
while the ``cards.fsrs_state`` column is ``jsonb`` (a dict); this service converts between the two
at the boundary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fsrs import Rating
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.repositories.cards import CardsRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.reviews import ReviewsRepository
from app.services.errors import NotFoundError, ValidationError
from lengua_core import config, proficiency, scheduler

_VALID_RATINGS = frozenset({1, 2, 3, 4})  # 1=Again 2=Hard 3=Good 4=Easy


@dataclass(frozen=True)
class GradeResult:
    """The outcome of grading one card."""

    card_id: int
    due: datetime
    score: float
    score_changed: bool


class ReviewService:
    """Select the due batch and grade cards for a user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cards = CardsRepository(session)
        self._reviews = ReviewsRepository(session)
        self._proficiency = ProficiencyRepository(session)

    async def due_batch(
        self,
        user_id: uuid.UUID,
        language_id: int,
        *,
        new_limit: int = config.DAILY_NEW_LIMIT,
        total_limit: int = config.DAILY_TOTAL_LIMIT,
    ) -> list[Card]:
        """Return the cards due now for the user, oldest-due first, capped by the given limits."""
        candidates = await self._cards.due_candidates(user_id, language_id)
        by_id: dict[int, Card] = {card.id: card for card in candidates}
        views = [self._scheduler_view(card) for card in candidates]
        batch = scheduler.select_due_batch(views, new_limit=new_limit, total_limit=total_limit)
        return [by_id[item["id"]] for item in batch]

    async def grade(self, user_id: uuid.UUID, card_id: int, rating: int) -> GradeResult:
        """Apply an FSRS ``rating`` (1..4) to a card: reschedule, log the review, nudge the level.

        Raises :class:`NotFoundError` if the card is not the user's and :class:`ValidationError`
        for an out-of-range rating or a card that has no FSRS state (not in the deck).
        """
        if rating not in _VALID_RATINGS:
            raise ValidationError(f"Rating must be one of 1..4, got {rating}.")
        card = await self._cards.get(user_id, card_id)
        if card is None:
            raise NotFoundError(f"Card {card_id} not found.")
        if card.fsrs_state is None:
            raise ValidationError(f"Card {card_id} has no FSRS state to grade.")

        rescheduled: tuple[str, str] = scheduler.apply_rating(
            json.dumps(card.fsrs_state), Rating(rating)
        )
        fsrs_json, due_iso = rescheduled
        new_state: dict[str, Any] = json.loads(fsrs_json)
        new_due = datetime.fromisoformat(due_iso)
        await self._cards.update_schedule(card, fsrs_state=new_state, due=new_due)
        await self._reviews.add(user_id, card_id, rating)

        current = await self._proficiency.get_score(user_id, card.language_id)
        new_score: float = proficiency.register_review(
            current, rating, card.direction, card.gen_level
        )
        changed = new_score != current
        if changed:
            await self._proficiency.upsert(user_id, card.language_id, new_score)

        await self._session.commit()
        return GradeResult(card_id=card_id, due=new_due, score=new_score, score_changed=changed)

    @staticmethod
    def _scheduler_view(card: Card) -> dict[str, Any]:
        """Adapt a ``Card`` row to the dict shape ``lengua_core.scheduler`` expects."""
        return {
            "id": card.id,
            "due": card.due.isoformat() if card.due is not None else None,
            "fsrs_state": json.dumps(card.fsrs_state) if card.fsrs_state is not None else None,
        }
