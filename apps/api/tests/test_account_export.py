"""``GET /account/export`` returns the user's full data bundle, scoped to them (task 2.8.1).

Two authenticated identities (A = the seeded ``DEV_USER_ID``, B = a token-only user given its own
``profiles`` row) each build a representative graph over the HTTP API — a language, a saved card
pair, a graded review (which also nudges proficiency), and a setting. The test then proves, over
the real router → service → repository stack, that:

* the export **schema** is the documented :class:`~app.schemas.account.AccountExport` (profile +
  languages + cards + reviews + proficiency + settings), and
* the bundle is **scoped to the caller**: A's export contains A's rows and *none* of B's, and B's
  export contains B's rows and none of A's — neither leaks the other's languages/cards/settings.

The endpoint takes no user-id parameter; the user is derived from the verified JWT (the
cross-tenant guard is asserted directly in ``tests/test_account_authz.py``).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.account import AccountExport
from scripts.seed_dev_user import DEV_USER_ID
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USER_A = uuid.UUID(DEV_USER_ID)
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


async def _provision(
    client: AsyncClient,
    user_id: uuid.UUID,
    *,
    language_name: str,
    word: str,
    setting_value: str,
) -> int:
    """Build a full per-user graph via the API: language → cards → graded review → setting.

    Returns the created ``language_id``.
    """
    headers = auth_header(user_id)

    created = await client.post(
        "/languages", json={"name": language_name, "code": "es"}, headers=headers
    )
    assert created.status_code == 200, created.text
    language_id = int(created.json()["id"])

    previews = await client.post(
        "/generate", json={"language_id": language_id, "words": [word]}, headers=headers
    )
    assert previews.status_code == 200, previews.text

    saved = await client.post(
        "/cards/save",
        json={"language_id": language_id, "cards": previews.json()},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    card_id = saved.json()[0]["id"]

    graded = await client.post(f"/review/{card_id}/grade", json={"rating": 3}, headers=headers)
    assert graded.status_code == 200, graded.text  # creates a review + upserts proficiency

    settings = await client.put(
        "/settings", json={"values": {"daily_total_limit": setting_value}}, headers=headers
    )
    assert settings.status_code == 200, settings.text
    return language_id


async def test_export_is_scoped_to_the_token_user(
    multiuser_client: AsyncClient, db_session: AsyncSession
) -> None:
    # B is a token-only identity; create its backing auth.users row so the handle_new_user trigger
    # bootstraps B's profile (the live schema's profiles.id -> auth.users(id) FK requires it). All
    # within the rolled-back db_session transaction, so nothing is committed.
    await db_session.execute(
        text("INSERT INTO auth.users (id, email) VALUES (:id, :email)"),
        {"id": USER_B, "email": "b-export@lengua.test"},
    )
    await db_session.flush()

    a_lang = await _provision(
        multiuser_client, USER_A, language_name="A-Spanish", word="hola", setting_value="20"
    )
    b_lang = await _provision(
        multiuser_client, USER_B, language_name="B-French", word="bonjour", setting_value="99"
    )

    # --- A's export: A's rows only ---
    a_resp = await multiuser_client.get("/account/export", headers=auth_header(USER_A))
    assert a_resp.status_code == 200, a_resp.text
    # It is offered as a downloadable file.
    assert "attachment" in a_resp.headers.get("content-disposition", "")

    bundle = AccountExport.model_validate(a_resp.json())  # exact schema (raises otherwise)
    assert bundle.profile is not None and bundle.profile.id == USER_A

    assert {lang.name for lang in bundle.languages} == {"A-Spanish"}
    assert {lang.id for lang in bundle.languages} == {a_lang}
    assert bundle.cards and all(c.language_id == a_lang for c in bundle.cards)
    assert bundle.reviews, "A graded a card, so there must be a review row"
    assert all(r.card_id in {c.id for c in bundle.cards} for r in bundle.reviews)
    assert [p.language_id for p in bundle.proficiency] == [a_lang]
    assert bundle.settings == {"daily_total_limit": "20"}

    # None of B's data leaks into A's bundle.
    all_a_text = a_resp.text
    assert "B-French" not in all_a_text
    assert "bonjour" not in all_a_text.lower()
    assert "99" not in {v for v in bundle.settings.values()}

    # --- B's export: B's rows only (symmetric) ---
    b_resp = await multiuser_client.get("/account/export", headers=auth_header(USER_B))
    assert b_resp.status_code == 200, b_resp.text
    b_bundle = AccountExport.model_validate(b_resp.json())
    assert b_bundle.profile is not None and b_bundle.profile.id == USER_B
    assert {lang.name for lang in b_bundle.languages} == {"B-French"}
    assert {lang.id for lang in b_bundle.languages} == {b_lang}
    assert b_bundle.settings == {"daily_total_limit": "99"}
    assert "A-Spanish" not in b_resp.text
    assert a_lang not in {lang.id for lang in b_bundle.languages}


async def test_export_for_user_without_a_profile_is_empty_not_leaky(
    multiuser_client: AsyncClient,
) -> None:
    """A token-only user with no rows gets a well-formed, empty bundle (``profile=None``)."""
    # A provisions data that must NOT appear in a stranger's export.
    await _provision(
        multiuser_client, USER_A, language_name="A-Spanish", word="hola", setting_value="20"
    )
    stranger = uuid.UUID("00000000-0000-0000-0000-0000000000e2")

    resp = await multiuser_client.get("/account/export", headers=auth_header(stranger))
    assert resp.status_code == 200, resp.text
    bundle = AccountExport.model_validate(resp.json())
    assert bundle.profile is None
    assert bundle.languages == []
    assert bundle.cards == []
    assert bundle.reviews == []
    assert bundle.proficiency == []
    assert bundle.settings == {}
