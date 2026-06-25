"""Integration tests for :class:`app.services.proficiency.ProficiencyService` (task 1.3.6).

Reads present score + band + progress; overrides set (and clamp) the score, by raw value or by
CEFR band. Unknown languages and bands are rejected.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.languages import LanguagesRepository
from app.services.errors import NotFoundError, ValidationError
from app.services.proficiency import ProficiencyService
from scripts.seed_e2e import SeedResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_get_default_and_overrides(
    db_session: AsyncSession, demo_account: SeedResult
) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Suomi", code="fi")
    service = ProficiencyService(db_session)

    # Default level when nothing recorded yet.
    default = await service.get(user_id, language.id)
    assert default.score == 0.0
    assert default.band == "A1"
    assert default.progress == 0.0

    # Override by raw score (B1 == floor(2.5)).
    view = await service.set_score(user_id, language.id, 2.5)
    assert view.score == pytest.approx(2.5)
    assert view.band == "B1"
    assert view.progress == pytest.approx(0.5)
    persisted = await service.get(user_id, language.id)
    assert persisted.score == pytest.approx(2.5)

    # Clamped to the C2 ceiling.
    clamped = await service.set_score(user_id, language.id, 99.0)
    assert clamped.score == pytest.approx(6.0)

    # Override by CEFR band (A2 -> 1.0).
    band_view = await service.set_band(user_id, language.id, "A2")
    assert band_view.band == "A2"
    assert band_view.score == pytest.approx(1.0)


async def test_validation_and_not_found(db_session: AsyncSession, demo_account: SeedResult) -> None:
    user_id = uuid.UUID(demo_account.user_id)
    language = await LanguagesRepository(db_session).create(user_id, "Íslenska", code="is")
    service = ProficiencyService(db_session)

    with pytest.raises(ValidationError):
        await service.set_band(user_id, language.id, "Z9")
    with pytest.raises(NotFoundError):
        await service.set_score(user_id, 10**9, 1.0)
