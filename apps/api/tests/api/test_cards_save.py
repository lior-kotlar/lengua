"""Task 1.5.4 verify: ``POST /cards/save`` persists a generated batch (``saved=true``).

Generates previews over HTTP, saves them, asserts the response rows are ``saved`` with real ids,
then reads the rows straight from the (shared) test session scoped to the dev user.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.repositories.cards import CardsRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_save_persists_scoped_to_dev_user(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    language_id = int(
        (await api_client.post("/languages", json={"name": "Spanish", "code": "es"})).json()["id"]
    )

    previews = (
        await api_client.post("/generate", json={"language_id": language_id, "words": ["hola"]})
    ).json()
    assert len(previews) == 2  # recognition + production

    resp = await api_client.post(
        "/cards/save", json={"language_id": language_id, "cards": previews}
    )
    assert resp.status_code == 200
    saved = resp.json()
    assert len(saved) == 2
    assert all(card["saved"] is True for card in saved)
    assert all(isinstance(card["id"], int) for card in saved)

    # The rows really exist, scoped to the dev user (the same session the request wrote through).
    rows = await CardsRepository(db_session).list_for_language(DEV_USER_ID, language_id, saved=True)
    assert len(rows) == 2
    assert {row.direction for row in rows} == {"recognition", "production"}


async def test_save_unknown_language_404(api_client: AsyncClient) -> None:
    card = {"direction": "recognition", "front": "Hola.", "back": "Hi.", "used_words": ["hola"]}
    resp = await api_client.post("/cards/save", json={"language_id": 999999, "cards": [card]})
    assert resp.status_code == 404
