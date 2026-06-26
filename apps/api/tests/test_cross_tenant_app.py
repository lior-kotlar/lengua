"""App-layer cross-tenant isolation (task 2.4.3).

User A (the seeded ``DEV_USER_ID``) creates a language, cards, and a review through the HTTP API.
User B is a *different* authenticated identity (a valid token, no rows of their own). The test
proves that, over the real router → service → repository stack, B can neither **read** nor
**mutate** A's data:

* B's ``GET /languages`` and ``GET /review/due`` never contain A's rows.
* B grading or deleting A's card/language returns ``404`` and leaves A's row untouched (checked
  directly against the DB).

This is the application half of tenant isolation; the DB half (RLS) is proven in group 2.6.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card, Language
from scripts.seed_dev_user import DEV_USER_ID
from tests.auth_helpers import auth_header

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USER_A = uuid.UUID(DEV_USER_ID)
# A distinct, token-only identity. B never inserts, so it needs no profile row.
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000b1")


async def _provision_user_a(client: AsyncClient) -> tuple[int, int]:
    """As user A: create a language, save a card pair, and grade one card.

    Returns ``(language_id, card_id)``.
    """
    headers = auth_header(USER_A)

    created = await client.post(
        "/languages", json={"name": "A-only", "code": "es"}, headers=headers
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]

    previews = await client.post(
        "/generate", json={"language_id": language_id, "words": ["hola"]}, headers=headers
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
    assert graded.status_code == 200, graded.text
    return language_id, card_id


async def test_user_b_cannot_read_or_mutate_user_a(
    multiuser_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id, card_id = await _provision_user_a(multiuser_client)
    headers_b = auth_header(USER_B)

    # --- B cannot READ A's rows ---
    b_languages = await multiuser_client.get("/languages", headers=headers_b)
    assert b_languages.status_code == 200
    assert b_languages.json() == []  # B owns nothing; A's language is invisible

    b_due = await multiuser_client.get(
        "/review/due", params={"language_id": language_id}, headers=headers_b
    )
    assert b_due.status_code == 200
    assert b_due.json() == {"new": [], "due": []}  # none of A's cards leak to B

    # B cannot read A's per-language proficiency (not their language).
    b_prof = await multiuser_client.get(f"/proficiency/{language_id}", headers=headers_b)
    assert b_prof.status_code == 404

    # --- B cannot MUTATE A's rows ---
    b_grade = await multiuser_client.post(
        f"/review/{card_id}/grade", json={"rating": 1}, headers=headers_b
    )
    assert b_grade.status_code == 404  # A's card is not found under B's scope

    b_delete = await multiuser_client.delete(f"/languages/{language_id}", headers=headers_b)
    assert b_delete.status_code == 404  # A's language is not found under B's scope

    # --- A's rows are untouched (verified directly against the DB) ---
    card = await db_session.get(Card, card_id)
    assert card is not None and card.user_id == USER_A
    language = await db_session.get(Language, language_id)
    assert language is not None and language.user_id == USER_A

    # And A can still see/operate on their own data.
    a_languages = await multiuser_client.get("/languages", headers=auth_header(USER_A))
    assert language_id in {row["id"] for row in a_languages.json()}
