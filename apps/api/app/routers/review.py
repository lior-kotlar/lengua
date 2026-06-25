"""Review router (task 1.5.5): ``GET /review/due`` (new vs due split) + grade a card."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db
from app.schemas.cards import CardOut
from app.schemas.review import DueResponse, GradeRequest, GradeResponse
from app.services.errors import NotFoundError, ValidationError
from app.services.review import GradeResult, ReviewService

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/due", response_model=DueResponse)
async def review_due(
    language_id: int,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> DueResponse:
    """Return the user's due batch for a language, split into new vs. previously-reviewed."""
    batch = await ReviewService(db).due_split(user_id, language_id)
    return DueResponse(
        new=[CardOut.model_validate(card) for card in batch.new],
        due=[CardOut.model_validate(card) for card in batch.due],
    )


@router.post("/{card_id}/grade", response_model=GradeResponse)
async def grade_card(
    card_id: int,
    body: GradeRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> GradeResult:
    """Grade a card (1=Again .. 4=Easy): FSRS reschedule + review log + proficiency nudge."""
    try:
        return await ReviewService(db).grade(user_id, card_id, body.rating)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
