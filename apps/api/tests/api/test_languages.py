"""Task 1.5.2 verify: ``POST -> GET -> DELETE /languages`` = 200/200/204, scoped to current_user."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_post_get_delete_language(api_client: AsyncClient) -> None:
    # POST -> 200, returns the created language.
    created = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "Spanish"
    assert body["code"] == "es"
    assert body["vowelized"] is False
    language_id = body["id"]

    # GET -> 200, the language is listed.
    listed = await api_client.get("/languages")
    assert listed.status_code == 200
    assert [lang["name"] for lang in listed.json()] == ["Spanish"]

    # DELETE -> 204, and it's gone.
    deleted = await api_client.delete(f"/languages/{language_id}")
    assert deleted.status_code == 204
    assert (await api_client.get("/languages")).json() == []


async def test_toggle_vowelized(api_client: AsyncClient) -> None:
    created = await api_client.post("/languages", json={"name": "Arabic", "code": "ar"})
    language_id = created.json()["id"]

    updated = await api_client.patch(f"/languages/{language_id}", json={"vowelized": True})
    assert updated.status_code == 200
    assert updated.json()["vowelized"] is True


async def test_add_blank_name_is_rejected(api_client: AsyncClient) -> None:
    # Pydantic min_length=1 rejects the empty/whitespace name -> 422.
    assert (await api_client.post("/languages", json={"name": "   "})).status_code == 422
    assert (await api_client.post("/languages", json={"name": ""})).status_code == 422


async def test_delete_unknown_language_404(api_client: AsyncClient) -> None:
    assert (await api_client.delete("/languages/999999")).status_code == 404


async def test_patch_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/languages/999999", json={"vowelized": True})
    assert resp.status_code == 404
