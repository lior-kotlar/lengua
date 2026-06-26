"""DTO for ``GET /me`` (task 2.3.2).

A minimal echo of the verified identity used as the JWT smoke-protected route. Task 2.4.4 expands
``/me`` to also return the profile plan + per-language proficiency for the authenticated user.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class MeOut(BaseModel):
    """The authenticated user's identity, derived solely from the verified access token."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None = None
    email_verified: bool
