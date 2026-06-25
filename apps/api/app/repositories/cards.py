"""Persistence for flashcards (task 1.3.3).

Like every repository this is the sole DB-touching layer and scopes every query by ``user_id``.
It deals in already-built rows: the *pure* card-building (sentence -> recognition + production
pair) and FSRS state live in ``lengua_core`` and are run by the generate/review services, which
hand finished values to :class:`NewCard` here. Keeping the building out of the repository is what
lets ``lengua_core`` stay DB-free and the repository stay logic-free.

Transaction control belongs to the service (see :mod:`app.repositories.languages`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card


@dataclass(frozen=True)
class NewCard:
    """A fully-prepared card row ready to persist (the repository's write contract).

    The service computes every field — direction/front/back from ``lengua_core.cards`` and
    ``fsrs_state``/``due`` from ``lengua_core.scheduler`` — so the repository only maps it onto a
    :class:`~app.db.models.Card` and inserts it.
    """

    front: str
    back: str
    direction: str
    used_words: list[str] | None
    word_explanations: dict[str, str] | None
    gen_level: float | None
    saved: bool
    fsrs_state: dict[str, Any] | None
    due: datetime | None


class CardsRepository:
    """Save card pairs and read the user's deck back, always scoped by ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_cards(
        self, user_id: uuid.UUID, language_id: int, cards: Sequence[NewCard]
    ) -> list[Card]:
        """Insert ``cards`` and return the persisted rows (with their generated ids)."""
        rows = [
            Card(
                user_id=user_id,
                language_id=language_id,
                front=c.front,
                back=c.back,
                direction=c.direction,
                used_words=c.used_words,
                word_explanations=c.word_explanations,
                gen_level=c.gen_level,
                saved=c.saved,
                fsrs_state=c.fsrs_state,
                due=c.due,
            )
            for c in cards
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def get(self, user_id: uuid.UUID, card_id: int) -> Card | None:
        """Return the user's card with ``card_id``, or ``None`` if not owned/absent."""
        stmt = select(Card).where(Card.user_id == user_id, Card.id == card_id)
        result = await self._session.scalars(stmt)
        return result.one_or_none()

    async def list_for_language(
        self, user_id: uuid.UUID, language_id: int, *, saved: bool | None = None
    ) -> Sequence[Card]:
        """Return the user's cards for a language (optionally filtered by ``saved``), id order."""
        stmt = select(Card).where(Card.user_id == user_id, Card.language_id == language_id)
        if saved is not None:
            stmt = stmt.where(Card.saved.is_(saved))
        stmt = stmt.order_by(Card.id)
        result = await self._session.scalars(stmt)
        return result.all()

    async def due_candidates(self, user_id: uuid.UUID, language_id: int) -> Sequence[Card]:
        """Saved cards with a ``due`` date — the candidate pool for the scheduler's batch pick."""
        stmt = select(Card).where(
            Card.user_id == user_id,
            Card.language_id == language_id,
            Card.saved.is_(True),
            Card.due.is_not(None),
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def update_schedule(
        self, card: Card, *, fsrs_state: dict[str, Any] | None, due: datetime | None
    ) -> Card:
        """Write back a graded card's new FSRS state and due date (row loaded via :meth:`get`)."""
        card.fsrs_state = fsrs_state
        card.due = due
        await self._session.flush()
        return card

    async def known_words(self, user_id: uuid.UUID, language_id: int) -> list[str]:
        """Deduplicated, sorted vocabulary the user has a saved card for (feeds Discover)."""
        stmt = select(Card.used_words).where(
            Card.user_id == user_id,
            Card.language_id == language_id,
            Card.saved.is_(True),
            Card.used_words.is_not(None),
        )
        result = await self._session.execute(stmt)
        words: set[str] = set()
        for (used,) in result.all():
            if used:
                words.update(used)
        return sorted(words)
