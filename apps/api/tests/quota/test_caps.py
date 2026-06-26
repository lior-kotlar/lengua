"""Per-user daily-cap gate tests (tasks 3.2.2 / 3.2.3).

* :func:`test_user_cap_clamped` exercises :func:`app.quota.resolve_user_cap`: a user-set cap above
  the hard server maximum resolves *down* to the maximum, an unset/blank/non-numeric setting falls
  back to the server default, and an in-range value passes through.
* :func:`test_daily_cap_blocks` exercises the gate (:meth:`app.quota.QuotaGuard.check` via
  :func:`app.quota.enforce_daily_cap`): with cap=2 a count of 1 is allowed and a count of 2 raises
  :class:`~app.quota.DailyCapReached` (the app maps that to HTTP 429).

Both touch the DB (``user_settings`` + the ``SECURITY DEFINER`` increment function), so they are
``@pytest.mark.integration`` and run against the local Supabase stack. They use the rolled-back
``db_session`` (superuser): its writes — including the increments and their global ``llm_budget``
bump — are undone at teardown, so nothing leaks between tests.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.quota import (
    DailyCapReached,
    QuotaGuard,
    _utc_today,
    enforce_daily_cap,
    resolve_user_cap,
)
from app.ratelimit import InProcessRateLimiter
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository
from app.settings import Settings
from scripts.seed_dev_user import seed_dev_user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _quota_settings() -> Settings:
    """Settings with explicit, env-independent quota ceilings (matches the documented defaults)."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        max_generate_per_day=50,
        max_discover_per_day=30,
        max_explain_per_day=100,
        default_generate_per_day=20,
        default_discover_per_day=10,
        default_explain_per_day=50,
    )


async def test_user_cap_clamped(db_session: AsyncSession) -> None:
    seed_dev_user()  # committed dev profile so the user_settings FK resolves
    settings = _quota_settings()
    repo = SettingsRepository(db_session)

    # A user-set cap above the hard server max resolves down to the max.
    await repo.upsert(DEV_USER_ID, "daily_cap_generate", "9999")
    assert await resolve_user_cap(db_session, settings, DEV_USER_ID, "generate") == 50

    # An unset cap resolves to the server default.
    assert await resolve_user_cap(db_session, settings, DEV_USER_ID, "discover") == 10

    # An in-range user value passes through unchanged.
    await repo.upsert(DEV_USER_ID, "daily_cap_explain", "7")
    assert await resolve_user_cap(db_session, settings, DEV_USER_ID, "explain") == 7

    # Blank / non-numeric overrides fall back to the default, never crash.
    await repo.upsert(DEV_USER_ID, "daily_cap_discover", "   ")
    assert await resolve_user_cap(db_session, settings, DEV_USER_ID, "discover") == 10
    await repo.upsert(DEV_USER_ID, "daily_cap_generate", "not-a-number")
    assert await resolve_user_cap(db_session, settings, DEV_USER_ID, "generate") == 20


async def test_daily_cap_blocks(db_session: AsyncSession) -> None:
    seed_dev_user()
    settings = _quota_settings()
    kind = "generate"
    today = _utc_today()

    # Cap this user's generate kind to 2.
    await SettingsRepository(db_session).upsert(DEV_USER_ID, "daily_cap_generate", "2")
    usage = UsageRepository(db_session)

    # count=1 < cap=2 → the gate allows (no exception).
    await usage.increment_usage(DEV_USER_ID, kind, today)
    assert await usage.get_user_daily_count(DEV_USER_ID, kind, today) == 1
    await enforce_daily_cap(db_session, settings, DEV_USER_ID, kind)  # does not raise

    # count=2 == cap=2 → the gate refuses with DailyCapReached carrying the kind.
    await usage.increment_usage(DEV_USER_ID, kind, today)
    assert await usage.get_user_daily_count(DEV_USER_ID, kind, today) == 2
    with pytest.raises(DailyCapReached) as exc_info:
        await enforce_daily_cap(db_session, settings, DEV_USER_ID, kind)
    assert exc_info.value.kind == kind

    # The same check via QuotaGuard.check (the dependency path) raises identically; a different kind
    # under the same user is unaffected (count still 0 < its cap). The guard runs the full chain, so
    # it is built email-verified with an unlimited limiter to isolate the cap gate.
    guard = QuotaGuard(
        kind=kind,
        user_id=DEV_USER_ID,
        email_verified=True,
        db=db_session,
        usage_db=db_session,  # type: ignore[arg-type]  # superuser session stands in for UsageSession
        settings=settings,
        rate_limiter=InProcessRateLimiter(limit=1000),
    )
    with pytest.raises(DailyCapReached):
        await guard.check()
    await enforce_daily_cap(db_session, settings, DEV_USER_ID, "discover")  # other kind: allowed
