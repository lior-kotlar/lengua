"""Persistence for review (grade) events (task 1.3.4).

One row per grade, with ``user_id`` denormalized alongside ``card_id`` so reviews can be scoped
(and, in Phase 2, RLS-filtered) without joining through ``cards``. The review service inserts a
row here as part of the same transaction in which it reschedules the card and nudges proficiency.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Review


class ReviewsRepository:
    """Insert review rows and read them back, scoped by ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: uuid.UUID, card_id: int, rating: int) -> Review:
        """Insert and return a review (FSRS rating 1..4) for ``user_id``'s ``card_id``."""
        review = Review(user_id=user_id, card_id=card_id, rating=rating)
        self._session.add(review)
        await self._session.flush()
        return review

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Review]:
        """Every review the user has recorded, oldest first (data export)."""
        stmt = select(Review).where(Review.user_id == user_id).order_by(Review.id)
        result = await self._session.scalars(stmt)
        return result.all()
