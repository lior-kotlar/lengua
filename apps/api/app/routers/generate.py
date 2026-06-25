"""Generate router (task 1.5.3): ``POST /generate`` -> created (unsaved) card previews."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, get_llm_provider
from app.schemas.generate import GeneratedCardModel, GenerateRequest
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core.cards import BuiltCard
from lengua_core.llm import LLMProvider

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=list[GeneratedCardModel])
async def generate(
    body: GenerateRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> list[BuiltCard]:
    """Generate recognition+production card previews for ``words`` (nothing is persisted yet)."""
    try:
        return await GenerateService(db, provider).generate(user_id, body.language_id, body.words)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
