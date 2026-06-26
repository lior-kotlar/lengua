"""Task 3.7.2 — signup-abuse day-0 guard.

A brand-new account (its ``profiles.created_at`` is on the current UTC day) gets a reduced first-day
``generate`` ceiling (``NEW_ACCOUNT_DAY0_GENERATE_CAP``), so it hits the wall sooner than an
established account with the *same* configured cap and usage. Exercised at the gate level via
:func:`app.quota.enforce_daily_cap`, toggling one account between day-0 and established, plus a
defensive no-profile case.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.quota import DailyCapReached, _utc_today, enforce_daily_cap
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository
from app.settings import Settings
from scripts.seed_dev_user import seed_dev_user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_DAY0_CAP = 5
_NORMAL_CAP = 20


def _settings() -> Settings:
    """Env-independent settings: normal generate cap 20, day-0 generate ceiling 5."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        max_generate_per_day=50,
        default_generate_per_day=_NORMAL_CAP,
        new_account_day0_generate_cap=_DAY0_CAP,
    )


async def _backdate(db_session: AsyncSession, days: int) -> None:
    """Move the dev profile's ``created_at`` ``days`` into the past (→ an established account)."""
    await db_session.execute(
        text("UPDATE profiles SET created_at = now() - make_interval(days => :d) WHERE id = :id"),
        {"d": days, "id": DEV_USER_ID},
    )
    db_session.expire_all()  # drop the identity-map copy so the next read sees the new created_at


async def test_new_account_cooldown(db_session: AsyncSession) -> None:
    seed_dev_user()  # profile re-created on the truncated table → created_at = today → day-0
    settings = _settings()
    today = _utc_today()
    usage = UsageRepository(db_session)

    # The account's own configured cap is generous (20), so only the day-0 clamp can hold it back.
    await SettingsRepository(db_session).upsert(DEV_USER_ID, "daily_cap_generate", str(_NORMAL_CAP))

    # Spend exactly the day-0 ceiling.
    for _ in range(_DAY0_CAP):
        await usage.increment_usage(DEV_USER_ID, "generate", today)
    assert await usage.get_user_daily_count(DEV_USER_ID, "generate", today) == _DAY0_CAP

    # Day-0 account: count == day-0 cap (5) → blocked, even though its configured cap is 20.
    with pytest.raises(DailyCapReached):
        await enforce_daily_cap(db_session, settings, DEV_USER_ID, "generate")

    # The SAME account, now established (created 10 days ago): the clamp lifts → 5 < 20, allowed.
    await _backdate(db_session, 10)
    await enforce_daily_cap(db_session, settings, DEV_USER_ID, "generate")  # does not raise

    # …and the established account only blocks once it reaches its real, higher cap (20).
    for _ in range(_NORMAL_CAP - _DAY0_CAP):  # bring the running count up to 20
        await usage.increment_usage(DEV_USER_ID, "generate", today)
    assert await usage.get_user_daily_count(DEV_USER_ID, "generate", today) == _NORMAL_CAP
    with pytest.raises(DailyCapReached):
        await enforce_daily_cap(db_session, settings, DEV_USER_ID, "generate")


async def test_missing_profile_treated_as_established(db_session: AsyncSession) -> None:
    """Defensive: a user with no profile row is not day-0-clamped (the gate above guarantees one).

    The resolved cap (default 20) is above the day-0 ceiling (5), so the clamp checks
    ``created_at`` — finds no profile — and treats the account as established, leaving the cap at
    20. With zero usage the gate then allows the call (no raise).
    """
    ghost = uuid.uuid4()  # no profiles / settings / usage rows
    await enforce_daily_cap(db_session, _settings(), ghost, "generate")
