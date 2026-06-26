"""``/me`` router (task 2.3.2): the JWT smoke-protected identity route.

Requires a valid Supabase access token and echoes the verified identity. This is the route that
exercises :func:`app.deps.get_current_user` end-to-end (401 without a token, 200 with one). Task
2.4.4 expands the response to include the profile plan + per-language proficiency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser
from app.deps import get_current_user
from app.schemas.me import MeOut

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeOut)
async def read_me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    """Return the authenticated user's identity (requires a valid Supabase JWT)."""
    return user
