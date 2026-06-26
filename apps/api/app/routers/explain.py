"""Explain router (task 1.5.7): ``POST /explain`` -> a tap-a-word explanation (cached)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, get_llm_provider
from app.quota import QuotaGuard, quota_guard
from app.schemas.explain import ExplainRequest, ExplainResponse
from app.services.errors import NotFoundError, ValidationError
from app.services.explain import ExplainService
from lengua_core.llm import LLMProvider

router = APIRouter(tags=["explain"])

# Module-level dependency singleton (evaluated once at import) so the factory call isn't in an
# argument default (ruff B008). Built ``enforce=False`` so the cap is checked inside ExplainService
# only on a cache miss (a cache hit must stay free).
_EXPLAIN_QUOTA = Depends(quota_guard("explain", enforce=False))


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    body: ExplainRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    guard: QuotaGuard = _EXPLAIN_QUOTA,
) -> ExplainResponse:
    """Explain a tapped word in a sentence (served from the card's cache when available).

    The ``guard`` is built **unchecked** and handed to ``ExplainService`` so the per-user daily
    ``explain`` cap is enforced (and counted) only on a cache miss — a cache hit stays free.
    """
    try:
        note = await ExplainService(db, provider).explain(
            user_id, body.language_id, body.word, body.sentence, body.translation, guard=guard
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return ExplainResponse(word=body.word, explanation=note)
