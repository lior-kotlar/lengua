"""Languages router (task 1.5.2): list/add/remove + edit fields, scoped to current_user."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Language
from app.deps import current_user, get_db
from app.schemas.languages import (
    LanguageCreate,
    LanguageCreateOut,
    LanguageOut,
    LanguageUpdate,
)
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


@router.post("", response_model=LanguageCreateOut)
async def add_language(
    body: LanguageCreate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LanguageCreateOut:
    """Add a language (idempotent on the per-user ``UNIQUE (user_id, name)``).

    The response ``created`` flag is ``True`` when a new language was inserted and ``False`` when
    the name already existed — in which case the existing row is returned unchanged, so a client
    can tell a fresh add from a re-add (and skip resetting an existing language's proficiency).
    Status stays 200 (the API's ``POST`` convention); the flag carries the signal.
    """
    try:
        language, created = await LanguagesService(db).add_language(
            user_id, body.name, code=body.code, vowelized=body.vowelized
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return LanguageCreateOut(
        id=language.id,
        name=language.name,
        code=language.code,
        vowelized=language.vowelized,
        created=created,
    )


@router.patch("/{language_id}", response_model=LanguageOut)
async def update_language(
    language_id: int,
    body: LanguageUpdate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Language:
    """Edit a language's fields (``name`` / ``code`` / ``vowelized``); a partial update.

    Only the fields present in the body are changed (``code`` may be sent as ``null`` to clear it).
    """
    try:
        return await LanguagesService(db).update_language(
            user_id, language_id, body.model_dump(exclude_unset=True)
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


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
