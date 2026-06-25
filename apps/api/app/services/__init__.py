"""Service layer — orchestrates ``lengua_core`` (pure) + repositories, emits no SQL (task 1.3.6).

Routers (Phase 1.5) depend on these services, never on repositories or SQL directly. Each service
takes an :class:`~sqlalchemy.ext.asyncio.AsyncSession` (and, where it calls the model, an
:class:`~lengua_core.llm.base.LLMProvider`), wires up the repositories it needs, runs the pure
domain logic, and owns the transaction boundary (it commits its own writes).
"""

from __future__ import annotations

from app.services.discover import DiscoverService
from app.services.errors import NotFoundError, ServiceError, ValidationError
from app.services.generate import GenerateService
from app.services.languages import LanguagesService
from app.services.proficiency import ProficiencyService, ProficiencyView
from app.services.review import GradeResult, ReviewService
from app.services.settings import SettingsService

__all__ = [
    "DiscoverService",
    "GenerateService",
    "GradeResult",
    "LanguagesService",
    "NotFoundError",
    "ProficiencyService",
    "ProficiencyView",
    "ReviewService",
    "ServiceError",
    "SettingsService",
    "ValidationError",
]
