"""Languages router (task 1.5.2): list/add/remove + toggle ``vowelized``, scoped to current_user."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Language
from app.deps import current_user, get_db
from app.schemas.languages import LanguageCreate, LanguageOut, LanguageUpdate
from app.services.errors import NotFoundError, ValidationError
from app.services.languages import LanguagesService

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get("", response_model=list[LanguageOut])
async def list_languages(
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Sequence[Language]:
    """List the current user's languages, oldest first."""
    return await LanguagesService(db).list_languages(user_id)


@router.post("", response_model=LanguageOut)
async def add_language(
    body: LanguageCreate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Language:
    """Add a language (idempotent on the per-user ``UNIQUE (user_id, name)``)."""
    try:
        return await LanguagesService(db).add_language(
            user_id, body.name, code=body.code, vowelized=body.vowelized
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/{language_id}", response_model=LanguageOut)
async def set_vowelized(
    language_id: int,
    body: LanguageUpdate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Language:
    """Toggle a language's ``vowelized`` flag."""
    try:
        return await LanguagesService(db).set_vowelized(user_id, language_id, body.vowelized)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.delete("/{language_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_language(
    language_id: int,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a language (its cards/proficiency cascade)."""
    try:
        await LanguagesService(db).remove_language(user_id, language_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
