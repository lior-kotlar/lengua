"""Card DTOs (task 1.5.4): the save request and the persisted-card response."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.generate import GeneratedCardModel


class SaveCardsRequest(BaseModel):
    """Request body for ``POST /cards/save`` — the generate previews to persist."""

    language_id: int
    cards: list[GeneratedCardModel]


class CardOut(BaseModel):
    """A persisted flashcard row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    language_id: int
    direction: str | None
    front: str
    back: str
    used_words: list[str] | None
    word_explanations: dict[str, Any] | None
    gen_level: float | None
    saved: bool
    due: datetime | None
