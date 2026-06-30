"""Integration tests for :class:`app.services.settings.SettingsService` (task 1.3.6).

Get-all / get / set / set_many over the per-user key/value store, with blank-key validation, the
typed-numeric bounds + cross-field rule (finding S9), and delete-on-``None`` (finding S10).
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


async def test_out_of_bounds_numeric_rejected(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)
    for bad in (
        {"daily_new_limit": "0"},  # below min 1
        {"daily_new_limit": "101"},  # above max 100
        {"daily_total_limit": "501"},  # above max 500
        {"discover_count": "21"},  # above the DiscoverRequest.count max (20)
        {"daily_new_limit": "abc"},  # non-numeric
        {"daily_total_limit": "1.5"},  # non-integer
    ):
        with pytest.raises(ValidationError):
            await service.set_many(user_id, bad)
    # A rejected write persists nothing.
    assert await service.get_all(user_id) == {}


async def test_cross_field_new_exceeds_total_rejected(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)

    # Both in one request: new > total is refused (the S9 repro — the smaller total would win).
    with pytest.raises(ValidationError):
        await service.set_many(user_id, {"daily_new_limit": "100", "daily_total_limit": "1"})
    assert await service.get_all(user_id) == {}

    # Merge case: a later write of only the new limit is checked against the stored total.
    await service.set_many(user_id, {"daily_total_limit": "20"})
    with pytest.raises(ValidationError):
        await service.set_many(user_id, {"daily_new_limit": "50"})
    # The rejected write left the stored total untouched.
    assert await service.get_all(user_id) == {"daily_total_limit": "20"}


async def test_cross_field_within_total_ok(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)
    await service.set_many(user_id, {"daily_total_limit": "100"})
    await service.set_many(user_id, {"daily_new_limit": "30"})  # 30 <= 100
    assert await service.get_all(user_id) == {"daily_total_limit": "100", "daily_new_limit": "30"}


async def test_none_value_deletes_key(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    service = SettingsService(db_session)
    await service.set_many(user_id, {"discover_count": "8", "daily_total_limit": "40"})

    # A null value removes just that key (S10); the others remain.
    await service.set_many(user_id, {"discover_count": None})
    assert await service.get_all(user_id) == {"daily_total_limit": "40"}

    # set(key, None) deletes too (it delegates to set_many).
    await service.set(user_id, "daily_total_limit", None)
    assert await service.get_all(user_id) == {}
