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
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.quota import QuotaGuard, quota_guard
from app.schemas.cards import CardOut
from app.schemas.discover import DiscoverAcceptRequest, DiscoverRequest, DiscoverResponse
from app.services.discover import DiscoverService
from app.services.errors import NotFoundError
from lengua_core.llm import LLMProvider

router = APIRouter(prefix="/discover", tags=["discover"])

# Module-level dependency singletons (evaluated once at import) so the factory call isn't in an
# argument default (ruff B008). ``/discover`` is metered as ``discover``; ``/discover/accept``
# reuses the generate path and so is metered as ``generate``.
_DISCOVER_QUOTA = Depends(quota_guard("discover"))
_ACCEPT_QUOTA = Depends(quota_guard("generate"))


@router.post("", response_model=DiscoverResponse)
async def discover(
    body: DiscoverRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    limiter: LLMConcurrencyLimiter = Depends(get_llm_limiter),
    guard: QuotaGuard = _DISCOVER_QUOTA,
) -> DiscoverResponse:
    """Preview new words at the learner's level, excluding vocabulary they already know.

    Gated by the per-user daily ``discover`` cap (``quota_guard``) before the provider call, which
    runs under the global concurrency cap (``limiter``).
    """
    try:
        words = await DiscoverService(db, provider, limiter).suggest(
            user_id, body.language_id, count=body.count, topic=body.topic
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await guard.record_success()  # increments for the JWT user_id only (never client-supplied)
    return DiscoverResponse(words=words)


@router.post("/accept", response_model=list[CardOut])
async def accept(
    body: DiscoverAcceptRequest,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    limiter: LLMConcurrencyLimiter = Depends(get_llm_limiter),
    guard: QuotaGuard = _ACCEPT_QUOTA,
) -> list[Card]:
    """Generate and save cards for the accepted ``words`` (delegates to the generate flow).

    Accepting reuses the generate path, so it is gated and counted as ``generate`` (not
    ``discover``). The ``guard`` is handed to the service so the spend is counted right after the
    provider call and **before** the card persistence — a save failure then still counts the billed
    call (closing the billed-but-uncounted window) instead of skipping the increment. The id passed
    to the increment is always the JWT-derived ``user_id`` (never client-supplied).
    """
    try:
        cards = await DiscoverService(db, provider, limiter).accept(
            user_id, body.language_id, body.words, guard=guard
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return cards
