"""Integration tests for :class:`app.services.settings.SettingsService` (task 1.3.6).

Get-all / get / set / set_many over the per-user key/value store, with blank-key validation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import ValidationError
from app.services.settings import SettingsService
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_set_get_and_set_many(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)

    assert await service.get_all(user_id) == {}

    await service.set(user_id, "daily_total_limit", "30")
    assert await service.get(user_id, "daily_total_limit") == "30"
    await service.set(user_id, "daily_total_limit", "40")  # update in place
    assert await service.get(user_id, "daily_total_limit") == "40"

    await service.set_many(user_id, {"daily_new_limit": "5", "discover_count": "8"})
    assert await service.get_all(user_id) == {
        "daily_total_limit": "40",
        "daily_new_limit": "5",
        "discover_count": "8",
    }


async def test_blank_key_rejected(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)
    with pytest.raises(ValidationError):
        await service.set(user_id, "   ", "x")
    with pytest.raises(ValidationError):
        await service.set_many(user_id, {"ok": "1", "  ": "bad"})
