"""Per-user settings service (task 1.3.6).

A thin, validated wrapper over the settings repository for the user's preferences (daily review
limits, discover count, …). Reads return the full ``{key: value}`` map; writes upsert one or many
keys and commit. It holds no SQL of its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.settings import SettingsRepository
from app.services.errors import ValidationError


class SettingsService:
    """Read and upsert a user's key/value settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = SettingsRepository(session)

    async def get_all(self, user_id: uuid.UUID) -> dict[str, str | None]:
        """Return all of the user's settings as a mapping."""
        return await self._settings.get_all(user_id)

    async def get(self, user_id: uuid.UUID, key: str) -> str | None:
        """Return one setting's value, or ``None`` if unset."""
        return await self._settings.get(user_id, key)

    async def set(self, user_id: uuid.UUID, key: str, value: str | None) -> None:
        """Upsert a single setting and commit. Raises :class:`ValidationError` for a blank key."""
        clean_key = key.strip()
        if not clean_key:
            raise ValidationError("Setting key must not be empty.")
        await self._settings.upsert(user_id, clean_key, value)
        await self._session.commit()

    async def set_many(self, user_id: uuid.UUID, values: Mapping[str, str | None]) -> None:
        """Upsert several settings in one committed transaction (e.g. a settings form save)."""
        cleaned: list[tuple[str, str | None]] = []
        for key, value in values.items():
            clean_key = key.strip()
            if not clean_key:
                raise ValidationError("Setting key must not be empty.")
            cleaned.append((clean_key, value))
        for clean_key, value in cleaned:
            await self._settings.upsert(user_id, clean_key, value)
        await self._session.commit()
