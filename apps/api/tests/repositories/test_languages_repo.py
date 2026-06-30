"""Integration tests for :class:`app.repositories.languages.LanguagesRepository` (task 1.3.3).

Covers create / list / get / get_by_name / update / set_vowelized / delete, and proves every method
is scoped by ``user_id`` (a second user can neither see nor mutate the first user's languages).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.languages import LanguagesRepository
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000cc")


async def test_create_get_list_update_delete_scoped(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    repo = LanguagesRepository(db_session)

    alpha = await repo.create(user_id, "Lang Alpha", code="aa")
    beta = await repo.create(user_id, "Lang Beta", code="bb", vowelized=True)
    assert alpha.id != beta.id
    assert beta.vowelized is True

    names = {lang.name for lang in await repo.list_for_user(user_id)}
    assert {"Lang Alpha", "Lang Beta"} <= names

    got = await repo.get(user_id, alpha.id)
    assert got is not None and got.name == "Lang Alpha"
    by_name = await repo.get_by_name(user_id, "Lang Beta")
    assert by_name is not None and by_name.id == beta.id
    assert await repo.get_by_name(user_id, "nonexistent") is None

    # Scoped: another user can't read these rows.
    assert await repo.get(OTHER_USER, alpha.id) is None
    assert len(await repo.list_for_user(OTHER_USER)) == 0

    # update: a partial write touches only the present keys; absent keys are left untouched.
    edited = await repo.update(user_id, alpha.id, {"name": "Lang Alpha 2", "code": "a2"})
    assert edited is not None
    assert edited.name == "Lang Alpha 2"
    assert edited.code == "a2"
    assert edited.vowelized is False  # not in the change set -> unchanged
    # update is scoped/absent-safe (returns None) just like the other writers.
    assert await repo.update(OTHER_USER, alpha.id, {"code": "xx"}) is None
    assert await repo.update(user_id, 10**9, {"code": "xx"}) is None

    # set_vowelized (a thin wrapper over update): owned succeeds, scoped/absent returns None.
    updated = await repo.set_vowelized(user_id, alpha.id, True)
    assert updated is not None and updated.vowelized is True
    assert await repo.set_vowelized(OTHER_USER, alpha.id, True) is None
    assert await repo.set_vowelized(user_id, 10**9, True) is None

    # delete: owned succeeds (once), scoped/absent returns False.
    assert await repo.delete(OTHER_USER, beta.id) is False
    assert await repo.delete(user_id, alpha.id) is True
    assert await repo.get(user_id, alpha.id) is None
    assert await repo.delete(user_id, alpha.id) is False
