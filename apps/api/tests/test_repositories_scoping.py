"""Every repository method is scoped by the ``user_id`` it is passed (task 2.4.1).

The Phase 1 repositories already take an explicit ``user_id`` and filter ``WHERE user_id = :uid``
(no hard-coded dev user remains — the companion ``grep`` half of the verify). These integration
tests prove that behaviour end to end against real Postgres: data written for user A is invisible
to (and unmutatable by) a different ``user_id``, and write methods stamp the passed id onto the
row.

User A is the seeded demo account (a real ``profiles`` row — the FK requires it). The "other"
user is just a bare UUID used for read / failed-mutation probes, which never insert and so need
no profile row.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.reviews import ReviewsRepository
from app.repositories.settings import SettingsRepository
from scripts.seed_e2e import SeedResult
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A valid, distinct second user id. Only ever used for reads / failed mutations, so it needs no
# profile row (no insert references it).
OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


async def test_languages_repo_scoped(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    repo = LanguagesRepository(db_session)

    created = await repo.create(user_id, "Scoping-Lang", code="es")
    # create stamps the passed user_id onto the row.
    assert created.user_id == user_id

    # Reads filter by user_id: A sees the row; the other user sees nothing.
    assert (await repo.get(user_id, created.id)) is not None
    assert (await repo.get(OTHER_USER, created.id)) is None
    assert created.id in {row.id for row in await repo.list_for_user(user_id)}
    assert len(await repo.list_for_user(OTHER_USER)) == 0
    assert (await repo.get_by_name(user_id, "Scoping-Lang")) is not None
    assert (await repo.get_by_name(OTHER_USER, "Scoping-Lang")) is None

    # Writes filter by user_id: the other user cannot mutate or delete A's row.
    assert (await repo.set_vowelized(OTHER_USER, created.id, True)) is None
    assert (await repo.set_vowelized(user_id, created.id, True)) is not None
    assert (await repo.delete(OTHER_USER, created.id)) is False
    assert (await repo.delete(user_id, created.id)) is True


async def test_cards_repo_scoped(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Scoping-Cards", code="es")
    repo = CardsRepository(db_session)

    saved = await repo.save_cards(
        user_id,
        language.id,
        [make_new_card(back="una frase", used_words=["frase"], saved=True)],
    )
    # save_cards stamps the passed user_id onto each row.
    assert [row.user_id for row in saved] == [user_id]
    card_id = saved[0].id

    # Every read is user-scoped: A sees its deck, the other user sees nothing.
    assert (await repo.get(user_id, card_id)) is not None
    assert (await repo.get(OTHER_USER, card_id)) is None
    assert len(await repo.list_for_language(user_id, language.id)) == 1
    assert len(await repo.list_for_language(OTHER_USER, language.id)) == 0
    assert [c.id for c in await repo.due_candidates(user_id, language.id)] == [card_id]
    assert len(await repo.due_candidates(OTHER_USER, language.id)) == 0
    assert len(await repo.for_sentence(user_id, language.id, "una frase")) == 1
    assert len(await repo.for_sentence(OTHER_USER, language.id, "una frase")) == 0
    assert await repo.known_words(user_id, language.id) == ["frase"]
    assert await repo.known_words(OTHER_USER, language.id) == []


async def test_reviews_repo_scoped(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Scoping-Reviews", code="es")
    saved = await CardsRepository(db_session).save_cards(user_id, language.id, [make_new_card()])

    review = await ReviewsRepository(db_session).add(user_id, saved[0].id, 3)
    # add stamps the passed user_id onto the inserted review row.
    assert review.user_id == user_id
    assert review.card_id == saved[0].id


async def test_proficiency_repo_scoped(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Scoping-Prof", code="es")
    repo = ProficiencyRepository(db_session)

    await repo.upsert(user_id, language.id, 2.5)
    # The score is stored under (user_id, language_id); the other user reads the default floor.
    assert await repo.get_score(user_id, language.id) == pytest.approx(2.5)
    assert await repo.get_score(OTHER_USER, language.id) == 0.0


async def test_settings_repo_scoped(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    repo = SettingsRepository(db_session)

    await repo.upsert(user_id, "daily_new_limit", "15")
    # get / get_all are user-scoped: A reads its value, the other user reads nothing.
    assert await repo.get(user_id, "daily_new_limit") == "15"
    assert await repo.get(OTHER_USER, "daily_new_limit") is None
    assert await repo.get_all(user_id) == {"daily_new_limit": "15"}
    assert await repo.get_all(OTHER_USER) == {}
