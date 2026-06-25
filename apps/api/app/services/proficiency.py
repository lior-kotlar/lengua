"""Proficiency service: read the level and apply manual overrides (task 1.3.6).

Wraps the proficiency repository with the *pure* CEFR math in ``lengua_core.proficiency`` to
present a level as score + band + intra-band progress, and to let a user override their level
(by raw score or by CEFR band). Overrides are clamped to the valid range and committed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError, ValidationError
from lengua_core import config, proficiency


@dataclass(frozen=True)
class ProficiencyView:
    """A learner's level: continuous score, its CEFR band, and intra-band progress."""

    score: float
    band: str
    progress: float


class ProficiencyService:
    """Read and override a user's per-language proficiency."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proficiency = ProficiencyRepository(session)
        self._languages = LanguagesRepository(session)

    async def get(self, user_id: uuid.UUID, language_id: int) -> ProficiencyView:
        """Return the learner's level for one of their languages (0.0 / A1 if none recorded).

        Raises :class:`NotFoundError` if the language is not the user's, so a read never reports a
        level for a resource the caller does not own.
        """
        await self._require_language(user_id, language_id)
        score = await self._proficiency.get_score(user_id, language_id)
        return self._view(score)

    async def set_score(
        self, user_id: uuid.UUID, language_id: int, score: float
    ) -> ProficiencyView:
        """Manually set (and clamp) the score for a language. Raises if the language isn't owned."""
        await self._require_language(user_id, language_id)
        clamped: float = proficiency.clamp_score(score)
        await self._proficiency.upsert(user_id, language_id, clamped)
        await self._session.commit()
        return self._view(clamped)

    async def set_band(self, user_id: uuid.UUID, language_id: int, band: str) -> ProficiencyView:
        """Manually place the learner at a CEFR band (sets the score to its lower bound)."""
        if band not in config.CEFR_BANDS:
            raise ValidationError(f"Unknown CEFR band: {band!r}.")
        score: float = proficiency.score_for_band(band)
        return await self.set_score(user_id, language_id, score)

    async def _require_language(self, user_id: uuid.UUID, language_id: int) -> None:
        if await self._languages.get(user_id, language_id) is None:
            raise NotFoundError(f"Language {language_id} not found.")

    @staticmethod
    def _view(score: float) -> ProficiencyView:
        band: str = proficiency.band_for_score(score)
        progress: float = proficiency.band_progress(score)
        return ProficiencyView(score=score, band=band, progress=progress)
