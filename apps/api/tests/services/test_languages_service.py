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

    # Case-insensitive dedupe (issue #151): a differently-cased re-add resolves to the SAME row
    # (created=False) instead of inserting a case-variant duplicate — matching how the web picker
    # matches curated names case-insensitively.
    variant, variant_created = await service.add_language(user_id, "català")
    assert variant.id == created.id
    assert variant_created is False

    toggled = await service.update_language(user_id, created.id, {"vowelized": True})
    assert toggled.vowelized is True

    await service.remove_language(user_id, created.id)
    assert all(lang.id != created.id for lang in await service.list_languages(user_id))


async def test_update_edits_name_and_code_and_normalises(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    # A distinct right-to-left language (NOT "Hebrew", which the demo_account seed already owns —
    # renaming onto it would trip the per-user UNIQUE name guard). The scenario: a mistyped name
    # with no code is fixed post-creation and given its RTL code (S14).
    created, _ = await service.add_language(user_id, "Yidish")
    # name + code are editable post-creation (S14); inputs are trimmed.
    updated = await service.update_language(
        user_id, created.id, {"name": "  Yiddish  ", "code": "  yi  "}
    )
    assert updated.name == "Yiddish"
    assert updated.code == "yi"

    # A blank code is normalised to NULL; an absent key leaves a field untouched.
    cleared = await service.update_language(user_id, created.id, {"code": "   "})
    assert cleared.code is None
    assert cleared.name == "Yiddish"


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
    # ...case-insensitively too (issue #151): a differently-cased spelling of a name the user
    # already owns is still a conflict, not a distinct language.
    with pytest.raises(ValidationError):
        await service.update_language(user_id, second.id, {"name": "greek"})
    # Renaming to its OWN current name is fine (the conflict is itself).
    same = await service.update_language(user_id, first.id, {"name": "Greek"})
    assert same.name == "Greek"
    # ...including a pure case change of the row's own name (the conflict resolves to itself).
    recased = await service.update_language(user_id, first.id, {"name": "GREEK"})
    assert recased.name == "GREEK"


async def test_validation_and_not_found(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = LanguagesService(db_session)

    with pytest.raises(ValidationError):
        await service.add_language(user_id, "   ")
    with pytest.raises(NotFoundError):
        await service.update_language(user_id, 10**9, {"vowelized": True})
    with pytest.raises(NotFoundError):
        await service.remove_language(user_id, 10**9)
