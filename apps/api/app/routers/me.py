"""``/me`` router: the authenticated user's account overview (task 2.4.4).

Requires a valid Supabase access token (the JWT smoke-protected route from 2.3.2) and returns the
verified identity **plus** the user's profile ``plan`` and per-language proficiency levels — all
scoped to the token's user via :class:`~app.services.me.MeService` (never a client-supplied id),
so the response can only ever contain the caller's own data.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.deps import get_current_user, get_db
from app.schemas.me import LanguageLevel, MeOut
from app.services.me import MeService

router = APIRouter(tags=["account"])


@router.get("/me", response_model=MeOut)
async def read_me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeOut:
    """Return the authenticated user's identity, plan, and per-language proficiency levels."""
    view = await MeService(db).get(user.id)
    return MeOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        plan=view.plan,
        languages=[
            LanguageLevel(
                language_id=level.language_id,
                name=level.name,
                code=level.code,
                score=level.score,
                band=level.band,
                progress=level.progress,
            )
            for level in view.languages
        ],
    )
