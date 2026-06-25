"""Task 1.5.6 verify: ``POST /discover`` previews new words; the accept path produces cards.

Walks ``POST /discover`` (preview, excluding known vocabulary) then ``POST /discover/accept``
(generate + save the chosen words) over HTTP with the deterministic FakeLLM.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _new_language(api_client: AsyncClient, name: str = "Spanish") -> int:
    resp = await api_client.post("/languages", json={"name": name, "code": "es"})
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def test_discover_preview_then_accept(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)

    # Save a card whose used word ("house") is in FakeLLM's suggestion pool, so it's excluded.
    previews = (
        await api_client.post("/generate", json={"language_id": language_id, "words": ["house"]})
    ).json()
    assert (
        await api_client.post("/cards/save", json={"language_id": language_id, "cards": previews})
    ).status_code == 200

    # Preview: a list of new words, none of them already known.
    resp = await api_client.post("/discover", json={"language_id": language_id, "count": 5})
    assert resp.status_code == 200
    words = resp.json()["words"]
    assert len(words) == 5
    assert "house" not in words

    # Accept two words: two sentences -> a recognition + production card each (4 saved cards).
    accepted = await api_client.post(
        "/discover/accept", json={"language_id": language_id, "words": words[:2]}
    )
    assert accepted.status_code == 200
    cards = accepted.json()
    assert len(cards) == 4
    assert all(card["saved"] is True for card in cards)
    assert {card["direction"] for card in cards} == {"recognition", "production"}


async def test_discover_unknown_language_404(api_client: AsyncClient) -> None:
    assert (
        await api_client.post("/discover", json={"language_id": 999999, "count": 3})
    ).status_code == 404


async def test_accept_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/discover/accept", json={"language_id": 999999, "words": ["agua"]}
    )
    assert resp.status_code == 404


async def test_discover_count_out_of_range_422(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)
    # count is bounded 1..20 by the DTO.
    assert (
        await api_client.post("/discover", json={"language_id": language_id, "count": 0})
    ).status_code == 422
    assert (
        await api_client.post("/discover", json={"language_id": language_id, "count": 99})
    ).status_code == 422
