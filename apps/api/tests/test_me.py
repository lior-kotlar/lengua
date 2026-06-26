"""``GET /me`` returns the account overview scoped to the token's user (task 2.4.4).

``/me`` echoes the verified identity and adds the user's profile ``plan`` plus a per-language
proficiency level (score + CEFR band + progress). Everything is derived from the token's user id,
so user A's ``/me`` shows A's plan and languages and **never** B's, and a token-only user with no
profile gets the safe defaults (``plan='free'``, no languages).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Profile
from lengua_core import proficiency
from scripts.seed_dev_user import DEV_USER_ID
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USER_A = uuid.UUID(DEV_USER_ID)
# A distinct, token-only identity with no profile/language rows.
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


async def test_me_is_scoped_to_user_a(
    multiuser_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers_a = auth_header(USER_A, email="a@lengua.test")

    # Give A a non-default plan so /me proves it reads the real profile (not a hard-coded default).
    profile = await db_session.get(Profile, USER_A)
    assert profile is not None  # seeded by the multiuser_client fixture
    profile.plan = "pro"
    await db_session.flush()

    # A studies two languages; set a known proficiency on one of them.
    spanish = (
        await multiuser_client.post("/languages", json={"name": "Espanol"}, headers=headers_a)
    ).json()
    await multiuser_client.post("/languages", json={"name": "Francais"}, headers=headers_a)
    set_level = await multiuser_client.put(
        f"/proficiency/{spanish['id']}", json={"score": 2.0}, headers=headers_a
    )
    assert set_level.status_code == 200

    me = await multiuser_client.get("/me", headers=headers_a)
    assert me.status_code == 200
    body = me.json()
    assert body["id"] == str(USER_A)
    assert body["email"] == "a@lengua.test"
    assert body["email_verified"] is True
    assert body["plan"] == "pro"

    levels = {lang["name"]: lang for lang in body["languages"]}
    assert set(levels) == {"Espanol", "Francais"}
    # The language with a set score reports it (+ its derived band/progress).
    assert levels["Espanol"]["language_id"] == spanish["id"]
    assert levels["Espanol"]["score"] == pytest.approx(2.0)
    assert levels["Espanol"]["band"] == proficiency.band_for_score(2.0)
    assert 0.0 <= levels["Espanol"]["progress"] <= 1.0
    # The untouched language reports the A1 floor.
    assert levels["Francais"]["score"] == pytest.approx(0.0)
    assert levels["Francais"]["band"] == proficiency.band_for_score(0.0)


async def test_me_for_other_user_sees_only_their_own(
    multiuser_client: AsyncClient,
) -> None:
    # User A creates a language so there IS cross-tenant data to (not) leak.
    await multiuser_client.post("/languages", json={"name": "Espanol"}, headers=auth_header(USER_A))

    me = await multiuser_client.get("/me", headers=auth_header(USER_B, email="b@lengua.test"))
    assert me.status_code == 200
    body = me.json()
    assert body["id"] == str(USER_B)
    assert body["email"] == "b@lengua.test"
    # No profile row for B yet → the safe default plan, and none of A's languages.
    assert body["plan"] == "free"
    assert body["languages"] == []
