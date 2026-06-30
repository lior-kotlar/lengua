"""Integration tests for :class:`app.services.discover.DiscoverService` (task 1.3.6).

``suggest`` returns level-appropriate words excluding what the learner already knows; ``accept``
feeds chosen words straight into the generate flow and yields saved cards.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.discover_cache import DiscoverKey, InProcessDiscoverCache
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


class _StubProvider:
    """A focused ``LLMProvider`` double whose preview is a fixed word list, ignoring the prompt.

    It deliberately does *not* honour ``known_words``/``count`` or dedup itself — so a fixed list
    drives the service-layer guards directly: ``[]`` proves an empty preview is never cached (S8),
    and a noisy list (dupes, case-variants, blanks, an already-known word) proves the service
    filters + dedups before caching (S15). Only ``suggest_new_words`` is exercised by ``suggest``;
    the other ``LLMProvider`` methods aren't reached here (it is not subclassing the Any-typed
    ``FakeLLM``, which mypy --strict forbids).
    """

    def __init__(self, suggestions: list[str]) -> None:
        self._suggestions = suggestions

    def suggest_new_words(
        self,
        language: str,
        level_band: str,
        known_words: list[str],
        count: int = 5,
        topic: str | None = None,
    ) -> list[str]:
        return list(self._suggestions)


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


async def test_empty_preview_is_not_cached(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    """An empty preview must not be cached (S8): the next request retries, not stays empty."""
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Dansk", code="da")
    cache = _fresh_cache()
    discover = DiscoverService(db_session, _StubProvider([]), cache=cache)

    assert await discover.suggest(user_id, language.id, count=5, topic="food") == []

    # ``cache.get`` returns ``None`` (a true miss) rather than a cached ``[]`` — nothing was stored,
    # so a follow-up request will hit the provider again instead of being pinned to "no words".
    key = DiscoverKey(user_id=user_id, language_id=language.id, topic="food", count=5)
    assert cache.get(key) is None


async def test_suggest_filters_known_and_dedups(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    """Drops already-known + duplicate suggestions (case-insensitive), then trims to count (S15)."""
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Español", code="es")
    # Make "casa" a known word via a real saved card (its used word feeds ``known_words``).
    generate = GenerateService(db_session, FakeLLM())
    await generate.save(
        user_id, language.id, await generate.generate(user_id, language.id, ["casa"])
    )

    noisy = ["Casa", "agua", "Agua", "  pan  ", "pan", "leche", "sol", ""]
    discover = DiscoverService(db_session, _StubProvider(noisy), cache=_fresh_cache())
    suggestions = await discover.suggest(user_id, language.id, count=3)

    # "Casa" dropped (known, case-insensitive); "Agua"/"agua" collapse to one; blanks/dupes removed;
    # whitespace trimmed; the list capped at the requested count *after* the bad words are gone.
    assert suggestions == ["agua", "pan", "leche"]
