"""DTOs for ``GET /me``.

``/me`` returns the authenticated user's account overview: their verified identity (from the JWT),
their profile ``plan``, and a per-language proficiency level. The identity fields come from the
verified access token; ``plan`` and ``languages`` are read from the DB scoped to that user (task
2.4.4 — expanded from the 2.3 identity-only stub).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class LanguageLevel(BaseModel):
    """One of the user's languages with its current proficiency level."""

    model_config = ConfigDict(from_attributes=True)

    language_id: int
    name: str
    code: str | None = None
    score: float
    band: str
    progress: float


class MeOut(BaseModel):
    """The authenticated user's account overview (identity + plan + per-language levels)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None = None
    email_verified: bool
    plan: str
    languages: list[LanguageLevel]
