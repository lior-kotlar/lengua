"""Explain DTOs (task 1.5.7): the tap-a-word request and its (cached) explanation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    """Request body for ``POST /explain`` — a tapped word in a card's sentence.

    ``sentence`` is the target-language sentence (the production card's back) and ``translation``
    its English gloss, mirroring ``lengua_core.gemini.explain_word`` so any provider is a drop-in.
    """

    word: str = Field(min_length=1)
    sentence: str = Field(min_length=1)
    translation: str
    language_id: int


class ExplainResponse(BaseModel):
    """A short explanation of the tapped word (served from the card's cache when available)."""

    word: str
    explanation: str
