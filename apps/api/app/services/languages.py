"""Language management service (task 1.3.6).

Thin orchestration over :class:`~app.repositories.languages.LanguagesRepository`: it validates
input, makes ``add`` idempotent against the per-user ``UNIQUE (user_id, name)`` constraint, and
owns the transaction boundary (it commits its writes). It emits no SQL of its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

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
    ) -> tuple[Language, bool]:
        """Add a language; return ``(language, created)``.

        Idempotent on the per-user ``UNIQUE (user_id, name)``: when the name already exists the
        **existing** row is returned untouched with ``created=False`` — so a re-add never disturbs
        the learner's recorded proficiency (the caller skips the starting-band write on a re-add).
        ``created=True`` only when a new row was inserted.

        Raises :class:`ValidationError` when ``name`` is blank.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Language name must not be empty.")
        existing = await self._languages.get_by_name(user_id, clean_name)
        if existing is not None:
            return existing, False
        language = await self._languages.create(user_id, clean_name, code=code, vowelized=vowelized)
        await self._session.commit()
        return language, True

    async def update_language(
        self, user_id: uuid.UUID, language_id: int, changes: Mapping[str, object]
    ) -> Language:
        """Apply a partial update (``name`` / ``code`` / ``vowelized``) to the user's language.

        Normalises inputs (trims ``name``/``code``; an empty ``code`` becomes ``NULL``) and guards
        the per-user unique name. Only keys present in ``changes`` are touched. Raises
        :class:`ValidationError` on a blank or duplicate name, and :class:`NotFoundError` when the
        language isn't the user's.
        """
        clean: dict[str, object] = {}
        if "name" in changes:
            raw_name = changes["name"]
            new_name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not new_name:
                raise ValidationError("Language name must not be empty.")
            conflict = await self._languages.get_by_name(user_id, new_name)
            if conflict is not None and conflict.id != language_id:
                raise ValidationError(f"You already have a language named {new_name!r}.")
            clean["name"] = new_name
        if "code" in changes:
            raw_code = changes["code"]
            clean["code"] = (raw_code.strip() or None) if isinstance(raw_code, str) else raw_code
        if "vowelized" in changes:
            clean["vowelized"] = bool(changes["vowelized"])

        language = await self._languages.update(user_id, language_id, clean)
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
