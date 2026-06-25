"""Language management service (task 1.3.6).

Thin orchestration over :class:`~app.repositories.languages.LanguagesRepository`: it validates
input, makes ``add`` idempotent against the per-user ``UNIQUE (user_id, name)`` constraint, and
owns the transaction boundary (it commits its writes). It emits no SQL of its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Language
from app.repositories.languages import LanguagesRepository
from app.services.errors import NotFoundError, ValidationError


class LanguagesService:
    """List/add/update/remove a user's languages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._languages = LanguagesRepository(session)

    async def list_languages(self, user_id: uuid.UUID) -> Sequence[Language]:
        """Return all of the user's languages."""
        return await self._languages.list_for_user(user_id)

    async def add_language(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        code: str | None = None,
        vowelized: bool = False,
    ) -> Language:
        """Add a language (idempotent: returns the existing one if the name already exists).

        Raises :class:`ValidationError` when ``name`` is blank.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Language name must not be empty.")
        existing = await self._languages.get_by_name(user_id, clean_name)
        if existing is not None:
            return existing
        language = await self._languages.create(user_id, clean_name, code=code, vowelized=vowelized)
        await self._session.commit()
        return language

    async def set_vowelized(
        self, user_id: uuid.UUID, language_id: int, vowelized: bool
    ) -> Language:
        """Toggle a language's ``vowelized`` flag. Raises :class:`NotFoundError` if not owned."""
        language = await self._languages.set_vowelized(user_id, language_id, vowelized)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")
        await self._session.commit()
        return language

    async def remove_language(self, user_id: uuid.UUID, language_id: int) -> None:
        """Delete a language and its cards. Raises :class:`NotFoundError` if not found."""
        deleted = await self._languages.delete(user_id, language_id)
        if not deleted:
            raise NotFoundError(f"Language {language_id} not found.")
        await self._session.commit()
