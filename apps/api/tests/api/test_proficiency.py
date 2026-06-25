"""Task 1.5.8 verify: ``PUT /proficiency/{id}`` overrides the level; ``GET`` reads it back.

Covers the default level, a raw-score override (read back unchanged), a CEFR-band override, and
the not-found / validation paths.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _new_language(api_client: AsyncClient, name: str = "Spanish") -> int:
    resp = await api_client.post("/languages", json={"name": name, "code": "es"})
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def test_put_score_then_get(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)

    # Default level before any override.
    default = await api_client.get(f"/proficiency/{language_id}")
    assert default.status_code == 200
    assert default.json() == {"score": 0.0, "band": "A1", "progress": 0.0}

    # Override by raw score (B1 == floor(2.5), half-way through the band).
    put = await api_client.put(f"/proficiency/{language_id}", json={"score": 2.5})
    assert put.status_code == 200
    assert put.json()["band"] == "B1"

    # GET returns the new score back unchanged.
    got = await api_client.get(f"/proficiency/{language_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["score"] == pytest.approx(2.5)
    assert body["band"] == "B1"
    assert body["progress"] == pytest.approx(0.5)


async def test_put_band_override(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)
    put = await api_client.put(f"/proficiency/{language_id}", json={"band": "A2"})
    assert put.status_code == 200
    assert put.json()["band"] == "A2"
    assert (await api_client.get(f"/proficiency/{language_id}")).json()["score"] == pytest.approx(
        1.0
    )


async def test_get_unknown_language_404(api_client: AsyncClient) -> None:
    assert (await api_client.get("/proficiency/999999")).status_code == 404


async def test_put_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.put("/proficiency/999999", json={"score": 1.0})
    assert resp.status_code == 404


async def test_put_requires_exactly_one_field_422(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)
    # Neither field -> 422; both fields -> 422 (DTO validator enforces exactly one).
    assert (await api_client.put(f"/proficiency/{language_id}", json={})).status_code == 422
    both = await api_client.put(f"/proficiency/{language_id}", json={"score": 1.0, "band": "A2"})
    assert both.status_code == 422


async def test_put_unknown_band_422(api_client: AsyncClient) -> None:
    language_id = await _new_language(api_client)
    resp = await api_client.put(f"/proficiency/{language_id}", json={"band": "Z9"})
    assert resp.status_code == 422
