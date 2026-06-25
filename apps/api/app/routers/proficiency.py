"""Proficiency router (task 1.5.8): read the level and apply a manual override.

``GET /proficiency/{language_id}`` returns the learner's level (score + CEFR band + intra-band
progress); ``PUT`` overrides it by raw score or by CEFR band, both scoped to ``current_user``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db
from app.schemas.proficiency import ProficiencyOut, ProficiencyUpdate
from app.services.errors import NotFoundError, ValidationError
from app.services.proficiency import ProficiencyService

router = APIRouter(prefix="/proficiency", tags=["proficiency"])


@router.get("/{language_id}", response_model=ProficiencyOut)
async def get_proficiency(
    language_id: int,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProficiencyOut:
    """Return the learner's level for one of their languages."""
    try:
        view = await ProficiencyService(db).get(user_id, language_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProficiencyOut.model_validate(view)


@router.put("/{language_id}", response_model=ProficiencyOut)
async def set_proficiency(
    language_id: int,
    body: ProficiencyUpdate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProficiencyOut:
    """Override the level by raw ``score`` or CEFR ``band`` (exactly one; enforced by the DTO)."""
    service = ProficiencyService(db)
    try:
        if body.score is not None:
            view = await service.set_score(user_id, language_id, body.score)
        else:
            assert body.band is not None  # guaranteed by ProficiencyUpdate's validator
            view = await service.set_band(user_id, language_id, body.band)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return ProficiencyOut.model_validate(view)
