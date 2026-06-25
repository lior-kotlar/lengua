"""Generate DTOs (task 1.5.3).

:class:`GeneratedCardModel` is the shape of one *unsaved, built* flashcard — the output of
``POST /generate`` and, round-tripped, the input items of ``POST /cards/save``. It mirrors
:class:`lengua_core.cards.BuiltCard` (``from_attributes`` lets it validate straight off one).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """Request body for ``POST /generate``."""

    language_id: int
    words: list[str] = Field(default_factory=list)


class GeneratedCardModel(BaseModel):
    """One built (unsaved) flashcard direction — a generate preview / a save input item."""

    model_config = ConfigDict(from_attributes=True)

    direction: str
    front: str
    back: str
    used_words: list[str]
    word_explanations: dict[str, str] | None = None
    gen_level: float | None = None
