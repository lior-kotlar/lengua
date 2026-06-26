"""Integration tests for :class:`app.services.discover.DiscoverService` (task 1.3.6).

``suggest`` returns level-appropriate words excluding what the learner already knows; ``accept``
feeds chosen words straight into the generate flow and yields saved cards.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.discover_cache import InProcessDiscoverCache
from app.repositories.languages import LanguagesRepository
from app.services.discover import DiscoverService
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core.llm.fake import FakeLLM
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _fresh_cache() -> InProcessDiscoverCache:
    """A fresh, isolated reuse cache so a service test never touches the process-wide singleton."""
    return InProcessDiscoverCache(ttl_seconds=300.0, clock=lambda: 0.0)


async def test_suggest_excludes_known_then_accept_creates_cards(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Dansk", code="da")
    # Save a card whose used word ("house") is in FakeLLM's suggestion pool, so it must be excluded.
    generate = GenerateService(db_session, FakeLLM())
    await generate.save(
        user_id, language.id, await generate.generate(user_id, language.id, ["house"])
    )

    discover = DiscoverService(db_session, FakeLLM(), cache=_fresh_cache())
    suggestions = await discover.suggest(user_id, language.id, count=5)
    assert len(suggestions) == 5
    assert "house" not in suggestions  # already known -> excluded

    created = await discover.accept(user_id, language.id, suggestions[:2])
    # Two accepted words -> two sentences -> a recognition + production card each.
    assert len(created) == 4
    assert all(card.saved for card in created)


async def test_suggest_unknown_language_raises(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    discover = DiscoverService(db_session, FakeLLM(), cache=_fresh_cache())
    with pytest.raises(NotFoundError):
        await discover.suggest(user_id, 10**9)
