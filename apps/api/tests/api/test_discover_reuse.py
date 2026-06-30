"""Task 3.6.3 verify: a repeated ``/discover`` within the reuse window reuses the prior preview.

A second identical ``/discover`` for the same ``(user, language, topic, count)`` within
``DISCOVER_REUSE_WINDOW_SECONDS`` returns the cached suggestions from the in-process reuse cache —
making **no** provider call (``FakeLLM.call_count`` unchanged) and burning **no** daily-cap/budget
count (it never spent the operator key). A request with a distinct topic or count is a different
cache key, so it misses and makes a real, counted provider call.

The ``api_client`` fixture installs a fresh reuse cache with a frozen clock, so the window never
expires mid-test and the global cache can't bleed across tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.repositories.usage import UsageRepository
from lengua_core.llm.fake import FakeLLM

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _new_language(api_client: AsyncClient, name: str = "Spanish") -> int:
    resp = await api_client.post("/languages", json={"name": name, "code": "es"})
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def test_repeat_reuses_preview(api_client: AsyncClient, db_session: AsyncSession) -> None:
    language_id = await _new_language(api_client)
    day = datetime.now(UTC).date()
    usage = UsageRepository(db_session)
    FakeLLM.reset_call_count()

    body = {"language_id": language_id, "count": 5, "topic": "food"}

    # First discover: cache miss → provider invoked once → counted.
    first = await api_client.post("/discover", json=body)
    assert first.status_code == 200
    words = first.json()["words"]
    assert words  # non-empty preview
    assert FakeLLM.call_count == 1
    assert await usage.get_user_daily_count(DEV_USER_ID, "discover", day) == 1

    # Second identical discover: cache HIT → same words, ZERO provider calls, NO further count.
    second = await api_client.post("/discover", json=body)
    assert second.status_code == 200
    assert second.json()["words"] == words
    assert FakeLLM.call_count == 1  # unchanged — the LLM was not called again
    assert await usage.get_user_daily_count(DEV_USER_ID, "discover", day) == 1  # unchanged


async def test_distinct_topic_or_count_misses(api_client: AsyncClient) -> None:
    """A different topic (or count) is a separate cache key → a fresh, billed provider call."""
    language_id = await _new_language(api_client)
    FakeLLM.reset_call_count()

    food5 = {"language_id": language_id, "count": 5, "topic": "food"}
    assert (await api_client.post("/discover", json=food5)).status_code == 200
    assert FakeLLM.call_count == 1

    # Different topic → miss → a second provider call.
    travel5 = {"language_id": language_id, "count": 5, "topic": "travel"}
    assert (await api_client.post("/discover", json=travel5)).status_code == 200
    assert FakeLLM.call_count == 2

    # Same topic but a different count → miss → a third provider call.
    food3 = {"language_id": language_id, "count": 3, "topic": "food"}
    assert (await api_client.post("/discover", json=food3)).status_code == 200
    assert FakeLLM.call_count == 3

    # The original (food, 5) is still cached → reuse, no further provider call.
    assert (await api_client.post("/discover", json=food5)).status_code == 200
    assert FakeLLM.call_count == 3


async def test_fresh_reroll_bypasses_cache_and_counts(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """An explicit reroll (``fresh=true``) bypasses the reuse cache: a fresh, *counted* call (S8).

    The cache would otherwise pin an identical reroll to the same words and — worse — serve it for
    free, hiding the real (billed) call behind the cache. ``fresh`` skips the lookup, so the
    provider runs again and the per-user daily ``discover`` cap is charged for it.
    """
    language_id = await _new_language(api_client)
    day = datetime.now(UTC).date()
    usage = UsageRepository(db_session)
    FakeLLM.reset_call_count()

    body = {"language_id": language_id, "count": 5, "topic": "food"}

    # Prime the cache: first discover is a miss → provider invoked once → counted.
    assert (await api_client.post("/discover", json=body)).status_code == 200
    assert FakeLLM.call_count == 1
    assert await usage.get_user_daily_count(DEV_USER_ID, "discover", day) == 1

    # A plain repeat reuses the cache → no provider call, no further count (the existing behaviour).
    assert (await api_client.post("/discover", json=body)).status_code == 200
    assert FakeLLM.call_count == 1
    assert await usage.get_user_daily_count(DEV_USER_ID, "discover", day) == 1

    # The same body with ``fresh=true`` bypasses the cache → the LLM runs again, and it IS counted.
    reroll = await api_client.post("/discover", json={**body, "fresh": True})
    assert reroll.status_code == 200
    assert FakeLLM.call_count == 2  # cache bypassed — a real provider call happened
    assert await usage.get_user_daily_count(DEV_USER_ID, "discover", day) == 2  # and it was charged
