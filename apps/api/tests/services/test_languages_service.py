"""Integration tests for :class:`app.services.languages.LanguagesService` (task 1.3.6).

Covers the orchestration the repository alone doesn't provide: name trimming + validation,
idempotent ``add`` against the per-user UNIQUE constraint, and not-found guards on update/remove.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import NotFoundError, ValidationError
from app.services.languages import LanguagesService
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_add_is_idempotent_and_trimmed(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    created = await service.add_language(user_id, "  Català  ", code="ca")
    assert created.name == "Català"  # trimmed
    again = await service.add_language(user_id, "Català")
    assert again.id == created.id  # idempotent, no duplicate

    assert any(lang.name == "Català" for lang in await service.list_languages(user_id))

    toggled = await service.set_vowelized(user_id, created.id, True)
    assert toggled.vowelized is True

    await service.remove_language(user_id, created.id)
    assert all(lang.id != created.id for lang in await service.list_languages(user_id))


async def test_validation_and_not_found(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    with pytest.raises(ValidationError):
        await service.add_language(user_id, "   ")
    with pytest.raises(NotFoundError):
        await service.set_vowelized(user_id, 10**9, True)
    with pytest.raises(NotFoundError):
        await service.remove_language(user_id, 10**9)
