"""Persistence for per-user key/value settings (task 1.3.5).

A small typed key/value store per user (daily review limits, discover count, …), keyed by the
``(user_id, key)`` composite PK. Writes are upserts so a setting can be created or changed with
one call; reads come back as a plain ``dict`` the settings service can interpret.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserSettings


class SettingsRepository:
    """Read-all, upsert, and delete per-user settings, always scoped by ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self, user_id: uuid.UUID) -> dict[str, str | None]:
        """Return all of the user's settings as a ``{key: value}`` mapping."""
        stmt = select(UserSettings.key, UserSettings.value).where(UserSettings.user_id == user_id)
        result = await self._session.execute(stmt)
        return {key: value for key, value in result.all()}

    async def get(self, user_id: uuid.UUID, key: str) -> str | None:
        """Return a single setting's value, or ``None`` if the user has not set it."""
        stmt = select(UserSettings.value).where(
            UserSettings.user_id == user_id, UserSettings.key == key
        )
        return await self._session.scalar(stmt)

    async def upsert(self, user_id: uuid.UUID, key: str, value: str | None) -> None:
        """Insert or update one setting for ``(user_id, key)``."""
        stmt = pg_insert(UserSettings).values(user_id=user_id, key=key, value=value)
        stmt = stmt.on_conflict_do_update(index_elements=["user_id", "key"], set_={"value": value})
        await self._session.execute(stmt)

    async def delete(self, user_id: uuid.UUID, key: str) -> None:
        """Delete one setting row for ``(user_id, key)`` — a no-op when it does not exist.

        Lets a write **remove** a key (finding S10), not only set it. Scoped by ``user_id`` (and by
        RLS), so a caller can only ever delete their own settings.
        """
        stmt = sql_delete(UserSettings).where(
            UserSettings.user_id == user_id, UserSettings.key == key
        )
        await self._session.execute(stmt)
