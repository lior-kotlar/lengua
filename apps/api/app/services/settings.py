"""Per-user settings service (task 1.3.6).

A thin, validated wrapper over the settings repository for the user's preferences (daily review
limits, discover count, …). Reads return the full ``{key: value}`` map; writes upsert or
delete one or many keys, then commit. It holds no SQL of its own.

**Write-side validation (findings S9 / S10).** The store is a generic string map, but a few
keys are parsed as integers downstream — the review-batch limits by ``GET /review/due``, and
``discover_count`` by the Discover form — so the write path:

* bounds-checks those typed numeric keys and enforces the cross-field rule
  ``daily_new_limit <= daily_total_limit`` over the *post-merge* state. Without it a caller could
  persist e.g. ``daily_new_limit=100000`` with ``daily_total_limit=1``; the review batch caps the
  whole batch at the smaller total, so the surplus "new" cards would never appear (S9). A violation
  raises :class:`ValidationError`, surfaced as **422** by the router, before anything is written.
  The bounds live here (not on the request model) so the OpenAPI contract stays neutral, and they
  mirror the product bounds the web Settings form uses (``apps/web/src/lib/settings.ts``) and the
  ``discover_count`` schema bound (``DiscoverRequest.count``).
* treats a ``None`` value as a **delete**, so a write can clear a key, not only set it — there was
  previously no way to remove a written key through the API (S10).

Keys not listed in :data:`NUMERIC_SETTING_BOUNDS` stay free-form strings, so a new preference still
needs no schema or migration.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.settings import SettingsRepository
from app.schemas.discover import DiscoverRequest
from app.services.errors import ValidationError
from app.services.review import (
    DAILY_NEW_LIMIT_KEY,
    DAILY_TOTAL_LIMIT_KEY,
    resolve_review_limit,
)
from lengua_core import config

#: ``user_settings`` key for the Discover form's default word count.
DISCOVER_COUNT_KEY = "discover_count"

# Single-source the discover_count bound from the ``DiscoverRequest.count`` schema (``ge``/``le``)
# so a stored preference can never exceed what ``POST /discover`` itself accepts — and so the two
# can never drift apart. (The daily-limit bounds below have no schema source: they are deliberately
# product bounds, kept out of the contract to keep S9 contract-neutral.)
_COUNT_SCHEMA = DiscoverRequest.model_json_schema()["properties"]["count"]

#: Inclusive ``(min, max)`` bounds for each typed integer settings key, enforced on write (S9).
#: ``daily_new_limit`` / ``daily_total_limit`` use the product bounds the web Settings form and the
#: legacy Streamlit page use; ``discover_count`` mirrors the ``DiscoverRequest.count`` schema bound.
NUMERIC_SETTING_BOUNDS: dict[str, tuple[int, int]] = {
    DAILY_NEW_LIMIT_KEY: (1, 100),
    DAILY_TOTAL_LIMIT_KEY: (1, 500),
    DISCOVER_COUNT_KEY: (int(_COUNT_SCHEMA["minimum"]), int(_COUNT_SCHEMA["maximum"])),
}


def validate_numeric_bound(key: str, value: str) -> None:
    """Raise :class:`ValidationError` if a typed-numeric ``key``'s ``value`` is invalid (S9).

    A no-op for any key not in :data:`NUMERIC_SETTING_BOUNDS` (the store stays generic). Otherwise
    the value — always a string in this store — must parse to an ``int`` within the key's inclusive
    bounds; surrounding whitespace is tolerated (parsed the same way the consumers read it). Pure,
    so the parse/range rules are unit-tested directly.
    """
    bounds = NUMERIC_SETTING_BOUNDS.get(key)
    if bounds is None:
        return
    low, high = bounds
    try:
        parsed = int(value.strip())
    except ValueError:
        raise ValidationError(f"Setting '{key}' must be a whole number.") from None
    if not low <= parsed <= high:
        raise ValidationError(f"Setting '{key}' must be between {low} and {high}.")


class SettingsService:
    """Read, upsert, and delete a user's key/value settings."""

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
        """Upsert a single setting — or delete it when ``value`` is ``None`` — and commit.

        A convenience wrapper over :meth:`set_many`, so the same blank-key, bounds, and cross-field
        validation applies. Raises :class:`ValidationError` for a blank key or an out-of-bounds
        typed-numeric value.
        """
        await self.set_many(user_id, {key: value})

    async def set_many(self, user_id: uuid.UUID, values: Mapping[str, str | None]) -> None:
        """Upsert (or delete) several settings in one committed transaction (e.g. a form save).

        Validates the whole batch first — a blank key or an out-of-bounds typed-numeric value raises
        :class:`ValidationError`, as does a post-merge ``daily_new_limit > daily_total_limit`` — so
        nothing is written when any entry is invalid (all-or-nothing). A ``None`` value deletes that
        key; any other value upserts it.
        """
        cleaned: list[tuple[str, str | None]] = []
        for key, value in values.items():
            clean_key = key.strip()
            if not clean_key:
                raise ValidationError("Setting key must not be empty.")
            if value is not None:
                validate_numeric_bound(clean_key, value)
            cleaned.append((clean_key, value))

        await self._check_review_limit_cross_field(user_id, cleaned)

        for clean_key, value in cleaned:
            if value is None:
                await self._settings.delete(user_id, clean_key)
            else:
                await self._settings.upsert(user_id, clean_key, value)
        await self._session.commit()

    async def _check_review_limit_cross_field(
        self, user_id: uuid.UUID, cleaned: list[tuple[str, str | None]]
    ) -> None:
        """Enforce ``daily_new_limit <= daily_total_limit`` over the post-merge limits (S9).

        Runs only when this write touches a review-limit key, so a PUT of unrelated settings is
        never blocked by a pre-existing inconsistency. Each limit's effective value is the value
        this write supplies (``None`` = deletion, which reverts it to the config default), else the
        currently stored value — each resolved exactly as ``GET /review/due`` resolves it (the
        ``lengua_core`` default for a missing / blank / non-numeric / non-positive value). Raises
        :class:`ValidationError` (→ 422) when the new-card limit would exceed the total.
        """
        incoming = dict(cleaned)
        if DAILY_NEW_LIMIT_KEY not in incoming and DAILY_TOTAL_LIMIT_KEY not in incoming:
            return
        stored = await self._settings.get_all(user_id)

        def effective(key: str, default: int) -> int:
            raw = incoming[key] if key in incoming else stored.get(key)
            return resolve_review_limit(raw, default)

        new_limit = effective(DAILY_NEW_LIMIT_KEY, config.DAILY_NEW_LIMIT)
        total_limit = effective(DAILY_TOTAL_LIMIT_KEY, config.DAILY_TOTAL_LIMIT)
        if new_limit > total_limit:
            raise ValidationError(
                f"daily_new_limit ({new_limit}) must not exceed "
                f"daily_total_limit ({total_limit})."
            )
