"""Discover router (task 1.5.6): preview new vocabulary, then accept it into the deck.

``POST /discover`` asks the provider for new words the learner does not already know (a preview,
nothing persisted); ``POST /discover/accept`` feeds the chosen words straight into the
generate+save flow, so accepting suggestions produces real, saved cards.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.deps import current_user, get_db, get_llm_provider
from app.schemas.cards import CardOut
from app.schemas.discover import DiscoverAcceptRequest, DiscoverRequest, DiscoverResponse
from app.services.discover import DiscoverService
from app.services.errors import NotFoundError
from lengua_core.llm import LLMProvider

router = APIRouter(prefix="/discover", tags=["discover"])


@router.post("", response_model=DiscoverResponse)
async def discover(
    body: DiscoverRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> DiscoverResponse:
    """Preview new words at the learner's level, excluding vocabulary they already know."""
    try:
        words = await DiscoverService(db, provider).suggest(
            user_id, body.language_id, count=body.count, topic=body.topic
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return DiscoverResponse(words=words)


@router.post("/accept", response_model=list[CardOut])
async def accept(
    body: DiscoverAcceptRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> list[Card]:
    """Generate and save cards for the accepted ``words`` (delegates to the generate flow)."""
    try:
        return await DiscoverService(db, provider).accept(user_id, body.language_id, body.words)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
