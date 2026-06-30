"""Integration tests for :class:`app.services.languages.LanguagesService` (task 1.3.6).

Covers the orchestration the repository alone doesn't provide: name trimming + validation,
idempotent ``add`` (with its created-vs-existing flag) against the per-user UNIQUE constraint,
the partial ``update`` of editable fields, and not-found guards on update/remove.
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

    created, was_created = await service.add_language(user_id, "  Català  ", code="ca")
    assert created.name == "Català"  # trimmed
    assert was_created is True
    again, again_created = await service.add_language(user_id, "Català")
    assert again.id == created.id  # idempotent, no duplicate
    assert again_created is False  # existing row -> created=False (the S3 signal)

    assert any(lang.name == "Català" for lang in await service.list_languages(user_id))

    toggled = await service.update_language(user_id, created.id, {"vowelized": True})
    assert toggled.vowelized is True

    await service.remove_language(user_id, created.id)
    assert all(lang.id != created.id for lang in await service.list_languages(user_id))


async def test_update_edits_name_and_code_and_normalises(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    created, _ = await service.add_language(user_id, "Ivrit")
    # name + code are editable post-creation (S14); inputs are trimmed.
    updated = await service.update_language(
        user_id, created.id, {"name": "  Hebrew  ", "code": "  he  "}
    )
    assert updated.name == "Hebrew"
    assert updated.code == "he"

    # A blank code is normalised to NULL; an absent key leaves a field untouched.
    cleared = await service.update_language(user_id, created.id, {"code": "   "})
    assert cleared.code is None
    assert cleared.name == "Hebrew"


async def test_update_rejects_blank_and_duplicate_name(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    first, _ = await service.add_language(user_id, "Greek", code="el")
    second, _ = await service.add_language(user_id, "Latin", code="la")

    # Blank name -> ValidationError.
    with pytest.raises(ValidationError):
        await service.update_language(user_id, second.id, {"name": "   "})
    # Renaming onto another of the user's languages -> ValidationError (per-user unique name).
    with pytest.raises(ValidationError):
        await service.update_language(user_id, second.id, {"name": "Greek"})
    # Renaming to its OWN current name is fine (the conflict is itself).
    same = await service.update_language(user_id, first.id, {"name": "Greek"})
    assert same.name == "Greek"


async def test_validation_and_not_found(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    with pytest.raises(ValidationError):
        await service.add_language(user_id, "   ")
    with pytest.raises(NotFoundError):
        await service.update_language(user_id, 10**9, {"vowelized": True})
    with pytest.raises(NotFoundError):
        await service.remove_language(user_id, 10**9)
