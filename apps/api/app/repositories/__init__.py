"""Repository layer — the **only** code that touches the domain tables (task 1.3.3-1.3.5).

Each repository wraps an :class:`~sqlalchemy.ext.asyncio.AsyncSession` and exposes async,
``user_id``-scoped methods; all SQL lives here so services and routers stay query-free and
``lengua_core`` stays DB-agnostic (the Phase 1 boundary rule; see the root ``CHANGELOG.md``).
Documented privileged-path exceptions live outside this package by design: the GDPR hard-delete
in ``app/services/account.py`` and the self-contained privileged readers ``app/prompt_store.py``
and ``app/feature_flags.py``.
"""

from __future__ import annotations

from app.repositories.cards import CardsRepository, NewCard
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.profiles import ProfilesRepository
from app.repositories.reviews import ReviewsRepository
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository

__all__ = [
    "CardsRepository",
    "LanguagesRepository",
    "NewCard",
    "ProficiencyRepository",
    "ProfilesRepository",
    "ReviewsRepository",
    "SettingsRepository",
    "UsageRepository",
]
