"""Account overview service for ``GET /me`` (task 2.4.4).

Assembles the authenticated user's account view from the DB: their profile ``plan`` plus a
per-language proficiency level (continuous score + CEFR band + intra-band progress). Everything is
read **scoped to the passed ``user_id``** (which the router derives from the verified JWT, never
from client input), so ``/me`` can only ever reflect the caller's own data — one half of the
tenant-isolation guarantee proven by ``tests/test_cross_tenant_app.py`` and ``tests/test_me.py``.

Like the other services it orchestrates repositories + the pure CEFR math in
``lengua_core.proficiency`` and emits no SQL of its own. It is read-only (no transaction/commit).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.profiles import ProfilesRepository
from lengua_core import proficiency

#: Fallback plan when no profile row exists yet (e.g. the trigger has not run). Matches the
#: ``profiles.plan`` DB default, so ``/me`` is robust for a brand-new identity.
DEFAULT_PLAN = "free"


@dataclass(frozen=True)
class LanguageLevelView:
    """One of the user's languages with its current proficiency level."""

    language_id: int
    name: str
    code: str | None
    score: float
    band: str
    progress: float


@dataclass(frozen=True)
class MeView:
    """The authenticated user's account view: plan + per-language levels."""

    plan: str
    languages: list[LanguageLevelView]


class MeService:
    """Build the ``/me`` account view for a single user."""

    def __init__(self, session: AsyncSession) -> None:
        self._profiles = ProfilesRepository(session)
        self._languages = LanguagesRepository(session)
        self._proficiency = ProficiencyRepository(session)

    async def get(self, user_id: uuid.UUID) -> MeView:
        """Return ``user_id``'s plan and per-language proficiency levels (oldest language first)."""
        profile = await self._profiles.get(user_id)
        plan = profile.plan if profile is not None else DEFAULT_PLAN

        languages = await self._languages.list_for_user(user_id)
        levels: list[LanguageLevelView] = []
        for language in languages:
            score = await self._proficiency.get_score(user_id, language.id)
            levels.append(
                LanguageLevelView(
                    language_id=language.id,
                    name=language.name,
                    code=language.code,
                    score=score,
                    band=proficiency.band_for_score(score),
                    progress=proficiency.band_progress(score),
                )
            )
        return MeView(plan=plan, languages=levels)
