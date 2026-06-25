"""Explain router (task 1.5.7): ``POST /explain`` -> a tap-a-word explanation (cached)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, get_llm_provider
from app.schemas.explain import ExplainRequest, ExplainResponse
from app.services.errors import NotFoundError, ValidationError
from app.services.explain import ExplainService
from lengua_core.llm import LLMProvider

router = APIRouter(tags=["explain"])


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    body: ExplainRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    """Explain a tapped word in a sentence (served from the card's cache when available)."""
    try:
        note = await ExplainService(db, provider).explain(
            user_id, body.language_id, body.word, body.sentence, body.translation
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return ExplainResponse(word=body.word, explanation=note)
