"""Task 5.2.2 verify: grading a card emits a ``review.grade`` span with the FSRS outcome.

Drives a real generate → save → ``POST /review/{id}/grade`` (FakeLLM, zero real LLM calls) and
asserts the ``review.grade`` span the service emits carries ``review.rating``, the reschedule result
(``review.next_due``), and the ``review.proficiency_delta``.

``@pytest.mark.integration`` — needs the local Supabase stack; auto-skips when the DB is down.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.deps import DEV_USER_ID
from app.services.review import (
    ATTR_REVIEW_NEXT_DUE,
    ATTR_REVIEW_PROFICIENCY_DELTA,
    ATTR_REVIEW_RATING,
    REVIEW_GRADE_SPAN_NAME,
)
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_grade_emits_review_grade_span(
    multiuser_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    headers = auth_header(DEV_USER_ID)
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
    card_id = saved.json()[0]["id"]

    span_exporter.clear()
    graded = await multiuser_client.post(
        f"/review/{card_id}/grade", json={"rating": 3}, headers=headers
    )
    assert graded.status_code == 200, graded.text

    spans = [s for s in span_exporter.get_finished_spans() if s.name == REVIEW_GRADE_SPAN_NAME]
    assert len(spans) == 1, f"expected one review.grade span, got {len(spans)}"
    attrs = dict(spans[0].attributes or {})

    assert attrs[ATTR_REVIEW_RATING] == 3
    # next_due is the FSRS reschedule result as an ISO-8601 string (parses back to a datetime).
    next_due = attrs[ATTR_REVIEW_NEXT_DUE]
    assert isinstance(next_due, str)
    assert datetime.fromisoformat(next_due)  # round-trips → a valid ISO-8601 instant
    # proficiency delta (new − previous) is recorded as a float (0.0 when the score didn't move).
    assert isinstance(attrs[ATTR_REVIEW_PROFICIENCY_DELTA], float)
