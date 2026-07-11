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
from collections.abc import Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Language

# The columns a ``PATCH`` may change. Constraining ``update`` to this allow-list keeps it from
# blindly writing arbitrary attributes off a caller-supplied mapping.
_EDITABLE_FIELDS = ("name", "code", "vowelized")


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
        """Return the user's language named ``name``, matched **case-insensitively**, or ``None``.

        The per-user ``UNIQUE (user_id, name)`` constraint is case-*sensitive* (``"French"`` and
        ``"french"`` are distinct rows at the DB level), but the app treats a language name as
        case-insensitive: the web picker matches curated names case-insensitively, so a curated
        "French" pick over an existing "french" must be recognised as the *same* language rather
        than inserting a case-variant duplicate row (issue #151). Matching on ``lower(name)`` here
        makes the service's idempotent-add dedupe and its rename-conflict guard agree with that.
        ``func.lower`` is portable across SQLite (tests) and Postgres (prod).

        Returns the **first** match in stable id order (``LIMIT 1``) rather than ``one_or_none``:
        if a user's data already held case-variant duplicates from before this fix, a broadened
        match must not raise ``MultipleResultsFound`` (a 500) — it just resolves to the oldest row.
        """
        stmt = (
            select(Language)
            .where(
                Language.user_id == user_id,
                func.lower(Language.name) == func.lower(name),
            )
            .order_by(Language.id)
            .limit(1)
        )
        result = await self._session.scalars(stmt)
        return result.first()

    async def update(
        self, user_id: uuid.UUID, language_id: int, changes: Mapping[str, object]
    ) -> Language | None:
        """Apply a partial update to the user's language; return the row, or ``None`` if not owned.

        Only the recognised, *present* keys in ``changes`` (``name`` / ``code`` / ``vowelized``)
        are written, so an absent key leaves its column untouched. Values are taken as-is — the
        service normalises/validates them before calling this.
        """
        language = await self.get(user_id, language_id)
        if language is None:
            return None
        for field in _EDITABLE_FIELDS:
            if field in changes:
                setattr(language, field, changes[field])
        await self._session.flush()
        return language

    async def set_vowelized(
        self, user_id: uuid.UUID, language_id: int, vowelized: bool
    ) -> Language | None:
        """Toggle the language's ``vowelized`` flag; return the row, or ``None`` if not owned."""
        return await self.update(user_id, language_id, {"vowelized": vowelized})

    async def delete(self, user_id: uuid.UUID, language_id: int) -> bool:
        """Delete the user's language (cards/proficiency cascade). ``True`` if a row was removed."""
        language = await self.get(user_id, language_id)
        if language is None:
            return False
        await self._session.delete(language)
        await self._session.flush()
        return True
