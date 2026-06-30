"""Task 1.5.2 verify: ``POST -> GET -> DELETE /languages`` = 200/200/204, scoped to current_user."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_post_get_delete_language(api_client: AsyncClient) -> None:
    # POST -> 200, returns the created language with created=True.
    created = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "Spanish"
    assert body["code"] == "es"
    assert body["vowelized"] is False
    assert body["created"] is True
    language_id = body["id"]

    # GET -> 200, the language is listed.
    listed = await api_client.get("/languages")
    assert listed.status_code == 200
    assert [lang["name"] for lang in listed.json()] == ["Spanish"]

    # DELETE -> 204, and it's gone.
    deleted = await api_client.delete(f"/languages/{language_id}")
    assert deleted.status_code == 204
    assert (await api_client.get("/languages")).json() == []


async def test_re_add_existing_name_is_idempotent(api_client: AsyncClient) -> None:
    # First add inserts a row -> created=True; re-adding the same name returns the existing row
    # unchanged -> created=False (the S3 signal the client uses to skip resetting proficiency).
    first = await api_client.post("/languages", json={"name": "Portuguese", "code": "pt"})
    assert first.status_code == 200
    assert first.json()["created"] is True

    again = await api_client.post("/languages", json={"name": "Portuguese", "code": "pt"})
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["id"] == first.json()["id"]


async def test_patch_edits_name_and_code(api_client: AsyncClient) -> None:
    # A language can be created with a blank code, then have its code/name edited later (S14).
    created = await api_client.post("/languages", json={"name": "עברית"})
    language_id = created.json()["id"]
    assert created.json()["code"] is None

    patched = await api_client.patch(
        f"/languages/{language_id}", json={"code": "he", "name": "Hebrew", "vowelized": True}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["code"] == "he"
    assert body["name"] == "Hebrew"
    assert body["vowelized"] is True


async def test_toggle_vowelized(api_client: AsyncClient) -> None:
    created = await api_client.post("/languages", json={"name": "Arabic", "code": "ar"})
    language_id = created.json()["id"]

    # A partial PATCH (only ``vowelized``) leaves the other fields untouched.
    updated = await api_client.patch(f"/languages/{language_id}", json={"vowelized": True})
    assert updated.status_code == 200
    assert updated.json()["vowelized"] is True
    assert updated.json()["code"] == "ar"
    assert updated.json()["name"] == "Arabic"


async def test_patch_blank_name_is_rejected(api_client: AsyncClient) -> None:
    created = await api_client.post("/languages", json={"name": "Italian", "code": "it"})
    language_id = created.json()["id"]
    # An explicit empty name on PATCH is rejected by the schema's min_length=1 -> 422.
    resp = await api_client.patch(f"/languages/{language_id}", json={"name": ""})
    assert resp.status_code == 422


async def test_add_blank_name_is_rejected(api_client: AsyncClient) -> None:
    # Pydantic min_length=1 rejects the empty/whitespace name -> 422.
    assert (await api_client.post("/languages", json={"name": "   "})).status_code == 422
    assert (await api_client.post("/languages", json={"name": ""})).status_code == 422


async def test_delete_unknown_language_404(api_client: AsyncClient) -> None:
    assert (await api_client.delete("/languages/999999")).status_code == 404


async def test_patch_unknown_language_404(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/languages/999999", json={"vowelized": True})
    assert resp.status_code == 404
