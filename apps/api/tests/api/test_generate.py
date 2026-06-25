"""Task 1.5.3 verify: ``POST /generate`` with a fake provider returns two cards per sentence.

Two words -> two sentences -> a recognition + production card each (4 total), every card tagged
with ``gen_level``. Nothing is persisted (these are previews).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _new_language(api_client: AsyncClient, name: str = "Spanish") -> int:
    resp = await api_client.post("/languages", json={"name": name, "code": "es"})
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def test_generate_two_words_returns_pairs(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)

    resp = await api_client.post(
        "/generate", json={"language_id": language_id, "words": ["hola", "gato"]}
    )
    assert resp.status_code == 200
    cards = resp.json()

    # Two words -> two sentences -> two cards (recognition + production) each.
    assert len(cards) == 4
    directions = [card["direction"] for card in cards]
    assert directions.count("recognition") == 2
    assert directions.count("production") == 2

    # gen_level is set on every preview (the learner's current score; 0.0 with no proficiency yet).
    assert all(card["gen_level"] == 0.0 for card in cards)

    # The deterministic FakeLLM echoes [language:band] into the sentence — proves the seam ran
    # with the resolved band, not a real model.
    assert any("[Spanish:A1]" in card["front"] for card in cards)


async def test_generate_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.post("/generate", json={"language_id": 999999, "words": ["x"]})
    assert resp.status_code == 404
