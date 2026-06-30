"""Generate router (task 1.5.3): ``POST /generate`` -> created (unsaved) card previews."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db, get_llm_provider
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.quota import QuotaGuard, quota_guard
from app.schemas.generate import GeneratedCardModel, GenerateRequest
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core.cards import BuiltCard
from lengua_core.llm import LLMProvider

router = APIRouter(tags=["generate"])

# Module-level dependency singleton (evaluated once at import) so the factory call isn't in an
# argument default (ruff B008); the per-user daily ``generate`` cap is checked before the body runs.
_GENERATE_QUOTA = Depends(quota_guard("generate"))


@router.post("/generate", response_model=list[GeneratedCardModel])
async def generate(
    body: GenerateRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    limiter: LLMConcurrencyLimiter = Depends(get_llm_limiter),
    guard: QuotaGuard = _GENERATE_QUOTA,
) -> list[BuiltCard]:
    """Generate recognition+production card previews for ``words`` (nothing is persisted yet).

    The ``quota_guard`` dependency enforces the per-user daily ``generate`` cap before the provider
    is called; on success we count the spend — but only when the call produced cards, so a no-op
    empty/blank-only request never burns a daily count (S11). The provider call runs under the
    global concurrency cap (``limiter``).
    """
    try:
        built = await GenerateService(db, provider, limiter).generate(
            user_id, body.language_id, body.words, guard=guard
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    # Count the spend only when cards were actually built (S11): blank-only input clears to nothing
    # service-side and yields zero cards, which must not consume a daily ``generate`` count. The
    # per-call observability span is finalized regardless by the ``quota_guard`` dependency
    # teardown. The increment always uses the JWT user_id only (never a client-supplied value).
    if built:
        await guard.record_success()
    return built
