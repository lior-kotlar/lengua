"""Task 3.3.3 — gate ordering: email-verified → rate-limit → daily-cap (→ global-budget).

A request that would fail multiple gates surfaces the **earliest** (highest-priority) failure. This
pins a user who simultaneously fails email + rate + cap, then relaxes the gates one at a time and
watches the surfaced error walk down the chain:

    403 email_unverified  →  429 rate_limited  →  429 daily_cap_reached

The provider is never called in any of the three cases.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.quota import _utc_today
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository
from lengua_core.llm.fake import FakeLLM
from tests.auth_helpers import authenticate_as
from tests.quota.conftest import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ``language_id`` is irrelevant in every case — a gate rejects the request before the route body
# (and thus the language lookup and the provider) ever runs.
_BODY = {"language_id": 1, "words": ["hola"]}


def _set_rate_limiter(app: FastAPI, limiter: RateLimiter) -> None:
    app.dependency_overrides[get_rate_limiter] = lambda: limiter


async def test_order(quota_app: FastAPI, db_session: AsyncSession) -> None:
    # Make the daily-cap gate want to block: cap generate to 1 and pre-spend 1 (so count >= cap).
    await SettingsRepository(db_session).upsert(DEV_USER_ID, "daily_cap_generate", "1")
    await UsageRepository(db_session).increment_usage(DEV_USER_ID, "generate", _utc_today())

    # Make the rate gate want to block: a limit-0 limiter rejects every request.
    _set_rate_limiter(quota_app, InProcessRateLimiter(limit=0))

    # 1) unverified email + rate-blocked + cap-exceeded → the EMAIL gate (first) wins: 403.
    authenticate_as(quota_app, DEV_USER_ID, email_verified=False)
    FakeLLM.reset_call_count()
    async with client_for(quota_app) as client:
        r = await client.post("/generate", json=_BODY)
    assert r.status_code == 403
    assert r.json() == {"code": "email_unverified"}
    assert FakeLLM.call_count == 0

    # 2) verify the email; still rate-blocked + cap-exceeded → the RATE gate (next) wins: 429.
    authenticate_as(quota_app, DEV_USER_ID, email_verified=True)
    async with client_for(quota_app) as client:
        r = await client.post("/generate", json=_BODY)
    assert r.status_code == 429
    assert r.json() == {"code": "rate_limited"}
    assert "Retry-After" in r.headers
    assert FakeLLM.call_count == 0

    # 3) relax the rate limit; still cap-exceeded → the DAILY-CAP gate (last) wins: 429.
    _set_rate_limiter(quota_app, InProcessRateLimiter(limit=1000))
    async with client_for(quota_app) as client:
        r = await client.post("/generate", json=_BODY)
    assert r.status_code == 429
    assert r.json() == {"code": "daily_cap_reached", "kind": "generate"}
    assert FakeLLM.call_count == 0
