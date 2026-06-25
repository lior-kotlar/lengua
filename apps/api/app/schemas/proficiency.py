"""Proficiency DTOs (task 1.5.8): the level view and the manual-override request."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProficiencyOut(BaseModel):
    """A learner's level for one language: continuous score, CEFR band, intra-band progress."""

    model_config = ConfigDict(from_attributes=True)

    score: float
    band: str
    progress: float


class ProficiencyUpdate(BaseModel):
    """Request body for ``PUT /proficiency/{language_id}`` — override by score *or* CEFR band.

    Exactly one of ``score`` / ``band`` must be supplied; ``score`` is clamped to the valid
    range and ``band`` is mapped to that band's lower-bound score by the service.
    """

    score: float | None = None
    band: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> ProficiencyUpdate:
        if (self.score is None) == (self.band is None):
            raise ValueError("Provide exactly one of 'score' or 'band'.")
        return self
