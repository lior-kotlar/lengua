"""Repository layer — the **only** code that touches the database (task 1.3.3-1.3.5).

Each repository wraps an :class:`~sqlalchemy.ext.asyncio.AsyncSession` and exposes async,
``user_id``-scoped methods; all SQL lives here so services and routers stay query-free and
``lengua_core`` stays DB-agnostic (the Phase 1 boundary rule from ``03-backend.md``).
"""

from __future__ import annotations

from app.repositories.cards import CardsRepository, NewCard
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.reviews import ReviewsRepository
from app.repositories.settings import SettingsRepository

__all__ = [
    "CardsRepository",
    "LanguagesRepository",
    "NewCard",
    "ProficiencyRepository",
    "ReviewsRepository",
    "SettingsRepository",
]
