"""Task 5.2.5: the product counters + the ``active_users`` gauge.

The offline unit tests drive :mod:`app.product_metrics` directly (deterministic, no DB) and assert
``reviews_total`` / ``cards_created_total`` / ``signups_total`` increment as documented (signups
deduped per process, a zero card-save is a no-op) and that the ``active_users`` observable gauge
reports the distinct users seen in the window. ``test_active_users_window`` exercises the TTL prune
with an injected clock.

``test_http_flow_increments_product_counters`` (``@integration``) proves the **wiring**: a real
signup (``GET /me``) → card save (``POST /cards/save``) → review grade (``POST /review/{id}/grade``)
moves each counter through the service call sites, and ``active_users`` reflects the acting user.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app import product_metrics
from app.deps import DEV_USER_ID
from app.product_metrics import (
    ActiveUsers,
    record_cards_created,
    record_review,
    record_signup,
)
from tests.auth_helpers import auth_header
from tests.obs.conftest import counter_value, gauge_values


def test_active_users_window() -> None:
    """The rolling window counts recent users and prunes ones older than the window."""
    now = {"t": 1000.0}
    tracker = ActiveUsers(window_seconds=60.0, clock=lambda: now["t"])
    a, b = uuid.uuid4(), uuid.uuid4()

    tracker.mark(a)
    tracker.mark(b)
    assert tracker.count() == 2

    # Re-marking the same user is not double-counted (distinct users).
    tracker.mark(a)
    assert tracker.count() == 2

    # Advance past the window for ``a`` only (``b`` re-marked just before the jump stays fresh).
    now["t"] = 1030.0
    tracker.mark(b)
    now["t"] = 1075.0  # a last seen @1000 (>60s ago → expired); b last seen @1030 (45s ago → live)
    assert tracker.count() == 1

    tracker.reset()
    assert tracker.count() == 0


def test_product_counters_and_active_users_gauge(
    metric_reader: InMemoryMetricReader, reset_product_state: None
) -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    # Signups: deduped per process — the same user counts once, a distinct user adds another.
    record_signup(user_a)
    record_signup(user_a)
    record_signup(user_b)
    assert counter_value(metric_reader, "signups_total", {}) == 2

    # Reviews: one per graded card.
    record_review(user_a)
    record_review(user_b)
    assert counter_value(metric_reader, "reviews_total", {}) == 2

    # Cards created: by the number saved; a zero/negative save is a no-op.
    record_cards_created(user_a, 3)
    record_cards_created(user_a, 0)
    assert counter_value(metric_reader, "cards_created_total", {}) == 3

    # active_users reflects the two distinct users that were active.
    assert gauge_values(metric_reader, "active_users") == [2]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_http_flow_increments_product_counters(
    multiuser_client: AsyncClient,
    metric_reader: InMemoryMetricReader,
    reset_product_state: None,
) -> None:
    headers = auth_header(DEV_USER_ID)

    # Signup proxy: the post-login /me call (deduped) increments signups_total once.
    me = await multiuser_client.get("/me", headers=headers)
    assert me.status_code == 200, me.text
    await multiuser_client.get("/me", headers=headers)  # repeat → still one signup
    assert counter_value(metric_reader, "signups_total", {}) == 1

    created = await multiuser_client.post(
        "/languages", json={"name": "Spanish", "code": "es"}, headers=headers
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]

    gen = await multiuser_client.post(
        "/generate", json={"language_id": language_id, "words": ["hola"]}, headers=headers
    )
    assert gen.status_code == 200, gen.text
    saved = await multiuser_client.post(
        "/cards/save", json={"language_id": language_id, "cards": gen.json()}, headers=headers
    )
    assert saved.status_code == 200, saved.text
    cards = saved.json()
    assert cards  # the generate→save produced cards
    # cards_created_total bumped by exactly the number of cards persisted.
    assert counter_value(metric_reader, "cards_created_total", {}) == len(cards)

    # Grade one card → reviews_total increments.
    grade = await multiuser_client.post(
        f"/review/{cards[0]['id']}/grade", json={"rating": 3}, headers=headers
    )
    assert grade.status_code == 200, grade.text
    assert counter_value(metric_reader, "reviews_total", {}) == 1

    # The dev user was active across all of the above.
    assert gauge_values(metric_reader, "active_users") == [1]
    assert product_metrics._active_users.count() == 1
