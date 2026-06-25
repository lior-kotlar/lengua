"""Settings DTOs (task 1.5.9): the per-user key/value preferences map.

A small, generic string key/value store (daily review limits, discover count, …). Known keys
today: ``daily_total_limit``, ``daily_new_limit``, ``discover_count`` — the Phase 3 quota gate
reads these. Kept generic (not a fixed schema) so new preferences need no migration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    """All of the user's settings as a ``{key: value}`` map."""

    values: dict[str, str | None]


class SettingsUpdate(BaseModel):
    """Request body for ``PUT /settings`` — upsert (merge) one or more settings.

    Only the keys present are written; existing keys not listed are left untouched.
    """

    values: dict[str, str] = Field(min_length=1)
