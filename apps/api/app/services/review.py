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
from collections.abc import Mapping
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

#: ``user_settings`` keys holding the per-user review-batch limits (each a stringified positive
#: int). They are read by the ``GET /review/due`` router and passed into
#: :meth:`ReviewService.due_split`; a missing / blank / non-numeric / non-positive value falls back
#: to the ``lengua_core.config`` default. (Distinct from the cost-guard ``daily_cap_*`` keys in
#: :mod:`app.quota`.)
DAILY_NEW_LIMIT_KEY = "daily_new_limit"
DAILY_TOTAL_LIMIT_KEY = "daily_total_limit"


def resolve_review_limit(raw: str | None, default: int) -> int:
    """Parse one per-user review-batch limit setting, falling back to ``default``.

    The settings store keeps values as strings, so this turns a stored ``daily_new_limit`` /
    ``daily_total_limit`` into the positive ``int`` :meth:`ReviewService.due_split` expects. A
    missing (``None``), blank, non-numeric, or non-positive value falls back to ``default`` — the
    ``lengua_core`` config default — so a cleared or malformed setting can never shrink the batch to
    nothing (or raise). Pure (no I/O), so the parse rules are unit-tested directly.
    """
    if raw is None:
        return default
    text = raw.strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    return value if value > 0 else default


def resolve_review_limits(settings: Mapping[str, str | None]) -> tuple[int, int]:
    """Resolve ``(new_limit, total_limit)`` from a user's settings map, with config fallbacks.

    Reads the :data:`DAILY_NEW_LIMIT_KEY` / :data:`DAILY_TOTAL_LIMIT_KEY` entries and parses each
    via :func:`resolve_review_limit` (defaulting to :data:`config.DAILY_NEW_LIMIT` /
    :data:`config.DAILY_TOTAL_LIMIT`), so the review router can hand the result straight to
    :meth:`due_split` without owning the parse rules itself.
    """
    new_limit = resolve_review_limit(settings.get(DAILY_NEW_LIMIT_KEY), config.DAILY_NEW_LIMIT)
    total_limit = resolve_review_limit(
        settings.get(DAILY_TOTAL_LIMIT_KEY), config.DAILY_TOTAL_LIMIT
    )
    return new_limit, total_limit


@dataclass(frozen=True)
class GradeResult:
    """The outcome of grading one card."""

    card_id: int
    due: datetime
    score: float
    score_changed: bool


@dataclass(frozen=True)
class DueBatch:
    """A due batch split into never-reviewed (``new``) vs. previously-seen (``due``) cards."""

    new: list[Card]
    due: list[Card]


class ReviewService:
    """Select the due batch and grade cards for a user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cards = CardsRepository(session)
        self._reviews = ReviewsRepository(session)
        self._proficiency = ProficiencyRepository(session)

    async def due_split(
        self,
        user_id: uuid.UUID,
        language_id: int,
        *,
        new_limit: int = config.DAILY_NEW_LIMIT,
        total_limit: int = config.DAILY_TOTAL_LIMIT,
    ) -> DueBatch:
        """Return the user's due batch split into never-reviewed (``new``) vs. ``due`` cards.

        New cards (no FSRS ``last_review``) are limited separately by ``new_limit`` so a big import
        doesn't bury reviews; the merged batch is capped at ``total_limit``. Each group keeps the
        scheduler's oldest-due-first order.
        """
        candidates = await self._cards.due_candidates(user_id, language_id)
        by_id: dict[int, Card] = {card.id: card for card in candidates}
        views = [self._scheduler_view(card) for card in candidates]
        batch = scheduler.select_due_batch(views, new_limit=new_limit, total_limit=total_limit)
        new_cards: list[Card] = []
        due_cards: list[Card] = []
        for item in batch:
            card = by_id[item["id"]]
            if scheduler.is_new_card(item):
                new_cards.append(card)
            else:
                due_cards.append(card)
        return DueBatch(new=new_cards, due=due_cards)

    async def due_batch(
        self,
        user_id: uuid.UUID,
        language_id: int,
        *,
        new_limit: int = config.DAILY_NEW_LIMIT,
        total_limit: int = config.DAILY_TOTAL_LIMIT,
    ) -> list[Card]:
        """Return the cards due now for the user as one flat list (reviewed first, then new)."""
        batch = await self.due_split(
            user_id, language_id, new_limit=new_limit, total_limit=total_limit
        )
        return batch.due + batch.new

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
