"""Task 3.2.4 verify: each LLM endpoint enforces its own per-user daily cap over HTTP.

Drives ``/generate``, ``/discover``, ``/discover/accept`` and ``/explain`` through the real app
(deterministic FakeLLM, no network) with each kind's per-user cap set to 2, and proves:

* exhausting one endpoint's cap returns HTTP 429 with the exact body
  ``{"code": "daily_cap_reached", "kind": <kind>}``;
* the cap is **per kind** — exhausting ``generate`` leaves ``discover``/``explain`` usable, and
  vice-versa (the counters are independent);
* ``/discover/accept`` is metered as ``generate`` (it reuses the generate path), not ``discover``;
* ``/explain`` is cache-aware — a cache **miss** is gated+counted, but a cache **hit** is free.

The cap is read from ``user_settings`` and the on-success increments go through the cost-guard's
usage session — both bound to the test's rolled-back ``db_session`` (see ``tests/api/conftest.py``),
so the counters never leak between tests and need no cleanup.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import DEV_USER_ID
from app.repositories.cards import CardsRepository
from app.repositories.settings import SettingsRepository
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CAP = 2
_SENTENCE = "El perro corre en el parque."
_TRANSLATION = "The dog runs in the park."


def _cap_body(kind: str) -> dict[str, str]:
    return {"code": "daily_cap_reached", "kind": kind}


async def _set_caps(db_session: AsyncSession) -> None:
    """Cap each kind to :data:`_CAP` for the dev user (uncommitted; the gate reads this session)."""
    repo = SettingsRepository(db_session)
    await repo.upsert(DEV_USER_ID, "daily_cap_generate", str(_CAP))
    await repo.upsert(DEV_USER_ID, "daily_cap_discover", str(_CAP))
    await repo.upsert(DEV_USER_ID, "daily_cap_explain", str(_CAP))


async def _new_language(api_client: AsyncClient) -> int:
    resp = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def _seed_production_card(db_session: AsyncSession, language_id: int) -> None:
    await CardsRepository(db_session).save_cards(
        DEV_USER_ID,
        language_id,
        [
            make_new_card(
                direction="production",
                front=_TRANSLATION,
                back=_SENTENCE,
                used_words=["perro", "parque"],
                word_explanations=None,
            )
        ],
    )


async def test_each_kind_capped(api_client: AsyncClient, db_session: AsyncSession) -> None:
    await _set_caps(db_session)
    language_id = await _new_language(api_client)
    await _seed_production_card(db_session, language_id)

    gen_body = {"language_id": language_id, "words": ["hola"]}

    # ── generate: two allowed, the third blocked ─────────────────────────────
    for _ in range(_CAP):
        assert (await api_client.post("/generate", json=gen_body)).status_code == 200
    blocked = await api_client.post("/generate", json=gen_body)
    assert blocked.status_code == 429
    assert blocked.json() == _cap_body("generate")

    # ── discover unaffected by generate's exhaustion (independent counter) ────
    disc_body = {"language_id": language_id, "count": 3}
    assert (await api_client.post("/discover", json=disc_body)).status_code == 200  # discover #1
    assert (await api_client.post("/discover", json=disc_body)).status_code == 200  # discover #2
    disc_blocked = await api_client.post("/discover", json=disc_body)
    assert disc_blocked.status_code == 429
    assert disc_blocked.json() == _cap_body("discover")

    # /discover/accept is metered as generate (already exhausted) → 429 with kind "generate".
    accept_blocked = await api_client.post(
        "/discover/accept", json={"language_id": language_id, "words": ["agua"]}
    )
    assert accept_blocked.status_code == 429
    assert accept_blocked.json() == _cap_body("generate")

    # ── explain unaffected by the above; a cache MISS is gated+counted ────────
    def explain_payload(word: str) -> dict[str, object]:
        return {
            "word": word,
            "sentence": _SENTENCE,
            "translation": _TRANSLATION,
            "language_id": language_id,
        }

    # Two distinct (uncached) words succeed and count; the third miss is blocked.
    first = await api_client.post("/explain", json=explain_payload("perro"))
    assert first.status_code == 200
    assert (await api_client.post("/explain", json=explain_payload("parque"))).status_code == 200
    explain_blocked = await api_client.post("/explain", json=explain_payload("corre"))
    assert explain_blocked.status_code == 429
    assert explain_blocked.json() == _cap_body("explain")

    # A cache HIT is free even though the cap is exhausted: re-tap an already-cached word → 200.
    cached = await api_client.post("/explain", json=explain_payload("perro"))
    assert cached.status_code == 200
    assert cached.json()["explanation"] == first.json()["explanation"]


async def test_generate_cap_does_not_block_unconfigured_user(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """With no per-user override, the generous server default applies — a normal call is allowed."""
    language_id = await _new_language(api_client)
    resp = await api_client.post("/generate", json={"language_id": language_id, "words": ["hola"]})
    assert resp.status_code == 200
    # The default generate cap is well above one call, so it is nowhere near tripping.
    assert isinstance(resp.json(), list)
