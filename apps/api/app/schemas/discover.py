"""Discover DTOs (task 1.5.6).

The two-step Discover UX: :class:`DiscoverRequest` previews new words the learner does not know
yet; :class:`DiscoverAcceptRequest` feeds the chosen words back into the generate+save flow.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoverRequest(BaseModel):
    """Request body for ``POST /discover`` — preview new vocabulary."""

    language_id: int
    # Bounded so a single request can't ask the provider for an unreasonable number of words
    # (mirrors the words-per-request cap on generation in task 1.2.5).
    count: int = Field(default=5, ge=1, le=20)
    topic: str | None = None
    # An explicit reroll ("Try different words"): bypass the short-window reuse cache so the learner
    # gets a freshly generated — billed and counted — set instead of the identical cached preview an
    # unchanged request would otherwise replay (finding S8). A normal first request leaves it false.
    fresh: bool = False


class DiscoverResponse(BaseModel):
    """The preview: new words the learner does not already have a card for."""

    words: list[str]


class DiscoverAcceptRequest(BaseModel):
    """Request body for ``POST /discover/accept`` — turn accepted words into saved cards."""

    language_id: int
    words: list[str] = Field(min_length=1)
