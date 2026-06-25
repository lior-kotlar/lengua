"""Persistence for a user's languages (task 1.3.3).

A repository is the **only** layer that touches the database: it owns the SQL/ORM statements and
nothing above it (services, routers) issues queries. Every method takes ``user_id`` explicitly
and scopes its query to it, so a caller can never read or mutate another user's rows — the
multi-tenant safety boundary the API depends on.

This repository carries no transaction control: it ``flush``es when it needs a server-generated
value (an identity id) but never commits. The owning service decides the unit-of-work boundary
and commits once, so a multi-write operation stays atomic.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Language


class LanguagesRepository:
    """Create/list/get/update/delete a user's languages, always scoped by ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        code: str | None = None,
        vowelized: bool = False,
    ) -> Language:
        """Insert and return a new language for ``user_id`` (id populated via ``flush``)."""
        language = Language(user_id=user_id, name=name, code=code, vowelized=vowelized)
        self._session.add(language)
        await self._session.flush()
        return language

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Language]:
        """Return the user's languages, oldest first (stable id order)."""
        stmt = select(Language).where(Language.user_id == user_id).order_by(Language.id)
        result = await self._session.scalars(stmt)
        return result.all()

    async def get(self, user_id: uuid.UUID, language_id: int) -> Language | None:
        """Return the user's language with ``language_id``, or ``None`` if not owned/absent."""
        stmt = select(Language).where(Language.user_id == user_id, Language.id == language_id)
        result = await self._session.scalars(stmt)
        return result.one_or_none()

    async def get_by_name(self, user_id: uuid.UUID, name: str) -> Language | None:
        """Return the user's language named ``name`` (the per-user UNIQUE key), or ``None``."""
        stmt = select(Language).where(Language.user_id == user_id, Language.name == name)
        result = await self._session.scalars(stmt)
        return result.one_or_none()

    async def set_vowelized(
        self, user_id: uuid.UUID, language_id: int, vowelized: bool
    ) -> Language | None:
        """Toggle the language's ``vowelized`` flag; return the row, or ``None`` if not owned."""
        language = await self.get(user_id, language_id)
        if language is None:
            return None
        language.vowelized = vowelized
        await self._session.flush()
        return language

    async def delete(self, user_id: uuid.UUID, language_id: int) -> bool:
        """Delete the user's language (cards/proficiency cascade). ``True`` if a row was removed."""
        language = await self.get(user_id, language_id)
        if language is None:
            return False
        await self._session.delete(language)
        await self._session.flush()
        return True
