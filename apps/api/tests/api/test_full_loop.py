"""Task 1.5.10 verify: the whole Generate -> Save -> Review -> grade -> Discover loop over HTTP.

Drives the complete core loop for the seeded dev user against a throwaway Postgres, asserting a
200 at every step and that the graded card is rescheduled to a *future* ``due`` (so it drops out
of the due batch). Exercises every router added in group 1.5b alongside the 1.5a core loop.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_full_generate_save_review_grade_discover_loop(api_client: AsyncClient) -> None:
    # 1) Add a language.
    lang_resp = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert lang_resp.status_code == 200
    language_id = int(lang_resp.json()["id"])

    # 2) Generate previews for two words -> two sentences -> 4 cards (recognition + production).
    gen_resp = await api_client.post(
        "/generate", json={"language_id": language_id, "words": ["hola", "gato"]}
    )
    assert gen_resp.status_code == 200
    previews = gen_resp.json()
    assert len(previews) == 4

    # 3) Save them into the deck.
    save_resp = await api_client.post(
        "/cards/save", json={"language_id": language_id, "cards": previews}
    )
    assert save_resp.status_code == 200
    assert len(save_resp.json()) == 4

    # 4) They appear in the due batch as new (never-reviewed) cards.
    due_resp = await api_client.get("/review/due", params={"language_id": language_id})
    assert due_resp.status_code == 200
    batch = due_resp.json()
    assert len(batch["new"]) == 4
    assert batch["due"] == []

    target = batch["new"][0]
    old_due = datetime.fromisoformat(target["due"])
    before_grade = datetime.now(UTC)

    # 5) Grade it Easy -> FSRS reschedules it into the future + nudges proficiency.
    grade_resp = await api_client.post(f"/review/{target['id']}/grade", json={"rating": 4})
    assert grade_resp.status_code == 200
    graded = grade_resp.json()
    new_due = datetime.fromisoformat(graded["due"])
    assert new_due > old_due
    assert new_due > before_grade  # a genuinely future due
    assert graded["score_changed"] is True
    assert graded["score"] > 0.0

    # 6) The grade moved the language level (Discover will generate at this band).
    prof_resp = await api_client.get(f"/proficiency/{language_id}")
    assert prof_resp.status_code == 200
    assert prof_resp.json()["score"] > 0.0

    # 7) The graded card has dropped out of the due batch (future due); 3 new cards remain.
    after = (await api_client.get("/review/due", params={"language_id": language_id})).json()
    remaining_ids = {card["id"] for card in after["new"]}
    assert target["id"] not in remaining_ids
    assert len(after["new"]) == 3

    # 8) Discover suggests new words, excluding what we already saved.
    discover_resp = await api_client.post(
        "/discover", json={"language_id": language_id, "count": 3}
    )
    assert discover_resp.status_code == 200
    words = discover_resp.json()["words"]
    assert len(words) == 3
    assert "hola" not in words and "gato" not in words

    # 9) Accept one suggestion -> a saved recognition + production pair, closing the loop.
    accept_resp = await api_client.post(
        "/discover/accept", json={"language_id": language_id, "words": words[:1]}
    )
    assert accept_resp.status_code == 200
    accepted = accept_resp.json()
    assert len(accepted) == 2
    assert all(card["saved"] is True for card in accepted)
