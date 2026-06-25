"""Integration tests for :class:`app.repositories.cards.CardsRepository` (task 1.3.3).

The headline verify: save a recognition + production *pair* for the seeded demo user and read it
back **scoped by ``user_id``** (a second user sees nothing). Also covers the deck reads the review
and discover services depend on (``due_candidates``, ``update_schedule``, ``known_words``).

All tests need the local Supabase Postgres and the seeded demo profile (the FK requires a real
``profiles`` row); they auto-skip when the DB is unreachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from scripts.seed_e2e import SeedResult
from tests.factories import make_new_card

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# An arbitrary, valid second user id for scoping checks (read queries don't need a profile row).
OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


async def test_save_pair_and_read_back_scoped(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Português", code="pt")
    cards = CardsRepository(db_session)

    due = datetime(2026, 1, 1, tzinfo=UTC)
    state = {"due": due.isoformat()}
    pair = [
        make_new_card(
            direction="recognition",
            front="Olá.",
            back="Hi.",
            used_words=["olá"],
            fsrs_state=state,
            due=due,
        ),
        make_new_card(
            direction="production",
            front="Hi.",
            back="Olá.",
            used_words=["olá"],
            word_explanations={"olá": "a greeting"},
            fsrs_state=state,
            due=due,
        ),
    ]
    saved = await cards.save_cards(user_id, language.id, pair)
    assert len(saved) == 2
    assert all(card.id is not None for card in saved)

    rows = await cards.list_for_language(user_id, language.id)
    assert len(rows) == 2
    assert {row.direction for row in rows} == {"recognition", "production"}
    # jsonb columns round-trip as native Python types.
    production = next(row for row in rows if row.direction == "production")
    assert production.used_words == ["olá"]
    assert production.word_explanations == {"olá": "a greeting"}
    assert production.fsrs_state == state

    # Scoped by user_id: a different user reads nothing and cannot fetch the row by id.
    assert len(await cards.list_for_language(OTHER_USER, language.id)) == 0
    assert await cards.get(OTHER_USER, saved[0].id) is None
    assert await cards.get(user_id, saved[0].id) is not None


async def test_list_filter_saved(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Magyar", code="hu")
    cards = CardsRepository(db_session)
    await cards.save_cards(
        user_id,
        language.id,
        [
            make_new_card(direction="recognition", saved=True),
            make_new_card(direction="production", saved=False, due=None),
        ],
    )
    assert len(await cards.list_for_language(user_id, language.id)) == 2
    assert len(await cards.list_for_language(user_id, language.id, saved=True)) == 1
    assert len(await cards.list_for_language(user_id, language.id, saved=False)) == 1


async def test_due_candidates_and_update_schedule(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Nederlands", code="nl")
    cards = CardsRepository(db_session)
    due = datetime(2026, 1, 1, tzinfo=UTC)
    saved = await cards.save_cards(
        user_id,
        language.id,
        [make_new_card(fsrs_state={"due": due.isoformat()}, due=due)],
    )
    # An unsaved card (no due) is excluded from the due candidate pool.
    await cards.save_cards(
        user_id, language.id, [make_new_card(saved=False, fsrs_state=None, due=None)]
    )

    candidates = await cards.due_candidates(user_id, language.id)
    assert [card.id for card in candidates] == [saved[0].id]

    new_due = datetime(2026, 2, 1, tzinfo=UTC)
    updated = await cards.update_schedule(candidates[0], fsrs_state={"step": 1}, due=new_due)
    assert updated.due == new_due

    refetched = await cards.get(user_id, saved[0].id)
    assert refetched is not None
    assert refetched.due == new_due
    assert refetched.fsrs_state == {"step": 1}


async def test_known_words_dedup_sorted_and_scoped(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Svenska", code="sv")
    cards = CardsRepository(db_session)
    await cards.save_cards(
        user_id,
        language.id,
        [
            make_new_card(used_words=["hej", "tack"], saved=True),
            make_new_card(used_words=["tack", "hus"], saved=True),
            make_new_card(used_words=[], saved=True),  # empty list contributes nothing
            make_new_card(used_words=["skip"], saved=False),  # unsaved → excluded
        ],
    )
    assert await cards.known_words(user_id, language.id) == ["hej", "hus", "tack"]
    assert await cards.known_words(OTHER_USER, language.id) == []
