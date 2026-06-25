"""Integration tests for :class:`app.repositories.settings.SettingsRepository` (task 1.3.5).

The verify: upsert a daily-limit setting and read it back. Also covers update-on-conflict,
``get_all``, the unset/``None`` cases, and ``user_id`` scoping.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.settings import SettingsRepository
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000dd")


async def test_upsert_then_read_back(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    repo = SettingsRepository(db_session)

    await repo.upsert(user_id, "daily_total_limit", "30")
    assert await repo.get(user_id, "daily_total_limit") == "30"

    # Upsert again updates in place (ON CONFLICT DO UPDATE).
    await repo.upsert(user_id, "daily_total_limit", "45")
    assert await repo.get(user_id, "daily_total_limit") == "45"

    await repo.upsert(user_id, "daily_new_limit", "7")
    assert await repo.get_all(user_id) == {"daily_total_limit": "45", "daily_new_limit": "7"}

    # Unset key is None; a NULL value round-trips as None.
    assert await repo.get(user_id, "missing") is None
    await repo.upsert(user_id, "nullable", None)
    assert await repo.get(user_id, "nullable") is None

    # Scoped: another user shares no settings.
    assert await repo.get_all(OTHER_USER) == {}
