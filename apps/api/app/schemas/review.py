"""Review DTOs (task 1.5.5): the due-batch split and the grade request/response."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cards import CardOut


class DueResponse(BaseModel):
    """The due batch for a language, split into never-reviewed (``new``) vs. ``due`` cards."""

    new: list[CardOut]
    due: list[CardOut]


class GradeRequest(BaseModel):
    """Request body for ``POST /review/{card_id}/grade`` — an FSRS rating 1..4."""

    rating: int = Field(ge=1, le=4)  # 1=Again 2=Hard 3=Good 4=Easy


class GradeResponse(BaseModel):
    """The outcome of grading a card."""

    model_config = ConfigDict(from_attributes=True)

    card_id: int
    due: datetime
    score: float
    score_changed: bool
