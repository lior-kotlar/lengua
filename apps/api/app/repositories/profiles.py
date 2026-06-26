"""Persistence for user profiles (task 2.4.4).

A profile row is 1:1 with an ``auth.users`` row (PK = the user's UUID) and carries the account
``plan``. Like every repository this is the only DB-touching layer; it is scoped by ``user_id``
implicitly because the user id *is* the primary key, so a lookup can only ever return the
caller's own row.

This repository is read-only for now (``/me``); the first-login *creation* of a profile is owned
by the ``handle_new_user`` Postgres trigger (Supabase) / task 2.5.1, not by app code.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Profile


class ProfilesRepository:
    """Read a user's profile, scoped by ``user_id`` (the primary key)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> Profile | None:
        """Return the profile whose id is ``user_id``, or ``None`` if it does not exist yet."""
        return await self._session.get(Profile, user_id)
