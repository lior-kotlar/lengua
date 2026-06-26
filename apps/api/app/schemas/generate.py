"""Generate DTOs (task 1.5.3).

:class:`GeneratedCardModel` is the shape of one *unsaved, built* flashcard — the output of
``POST /generate`` and, round-tripped, the input items of ``POST /cards/save``. It mirrors
:class:`lengua_core.cards.BuiltCard` (``from_attributes`` lets it validate straight off one).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.settings import get_settings

# The hard words-per-request ceiling, read once from settings at import (env-overridable via
# ``MAX_WORDS_PER_REQUEST``). Applied as the schema's ``max_length`` so an over-limit word list is
# rejected with **422** at the API boundary (a hard reject, not the silent ``cap_words`` truncation
# the providers still apply defensively) — the cheapest oversized call is the one we never make. It
# surfaces in the OpenAPI schema as ``maxItems`` on ``words``.
_MAX_WORDS_PER_REQUEST = get_settings().max_words_per_request


class GenerateRequest(BaseModel):
    """Request body for ``POST /generate``."""

    language_id: int
    words: list[str] = Field(default_factory=list, max_length=_MAX_WORDS_PER_REQUEST)


class GeneratedCardModel(BaseModel):
    """One built (unsaved) flashcard direction — a generate preview / a save input item."""

    model_config = ConfigDict(from_attributes=True)

    direction: str
    front: str
    back: str
    used_words: list[str]
    word_explanations: dict[str, str] | None = None
    gen_level: float | None = None
