"""Cards router (task 1.5.4): ``POST /cards/save`` persists generated card pairs into the deck."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.deps import current_user, get_db
from app.schemas.cards import CardOut, SaveCardsRequest
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core.cards import BuiltCard

router = APIRouter(prefix="/cards", tags=["cards"])


@router.post("/save", response_model=list[CardOut])
async def save_cards(
    body: SaveCardsRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Card]:
    """Persist generated recognition+production previews into the current user's deck (saved)."""
    built = [
        BuiltCard(
            direction=card.direction,
            front=card.front,
            back=card.back,
            used_words=card.used_words,
            word_explanations=card.word_explanations,
            gen_level=card.gen_level,
        )
        for card in body.cards
    ]
    try:
        return await GenerateService(db).save(user_id, body.language_id, built)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
