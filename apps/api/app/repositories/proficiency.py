"""Persistence for per-user, per-language proficiency scores (task 1.3.4).

The score is a single continuous CEFR value per ``(user_id, language_id)`` (the table's composite
PK), so writes are an **upsert**: the review service nudges it after a grade and the proficiency
service sets it on a manual override. The scoring math itself is pure and lives in
``lengua_core.proficiency`` — this layer only reads and upserts the number.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Proficiency


class ProficiencyRepository:
    """Read and upsert proficiency scores, scoped by ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_score(self, user_id: uuid.UUID, language_id: int) -> float:
        """Return the stored score, or ``0.0`` (CEFR floor / A1) when none is recorded yet."""
        stmt = select(Proficiency.score).where(
            Proficiency.user_id == user_id, Proficiency.language_id == language_id
        )
        score = await self._session.scalar(stmt)
        if score is None:
            return 0.0
        return float(score)

    async def upsert(self, user_id: uuid.UUID, language_id: int, score: float) -> float:
        """Insert or update the score for ``(user_id, language_id)``; return the stored value."""
        stmt = pg_insert(Proficiency).values(user_id=user_id, language_id=language_id, score=score)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "language_id"],
            set_={"score": score, "updated_at": func.now()},
        )
        await self._session.execute(stmt)
        return score
