"""Settings DTOs (task 1.5.9): the per-user key/value preferences map.

A small, generic string key/value store. It is intentionally **not** a fixed schema, so a new
preference needs no migration. Known keys today and where each is actually consumed:

* ``daily_new_limit`` / ``daily_total_limit`` — the review **due batch** (``GET /review/due`` →
  :meth:`app.services.review.ReviewService.due_split`): how many never-reviewed vs. total cards a
  single review session shows (each falls back to the ``lengua_core`` config default when unset).
* ``discover_count`` — the default number of new words ``POST /discover`` suggests.
* ``daily_cap_generate`` / ``daily_cap_discover`` / ``daily_cap_explain`` — the Phase 3 LLM
  cost-guard's per-kind daily caps, read by :func:`app.quota.resolve_user_cap` (these — **not** the
  ``daily_*_limit`` keys above — are what the quota gate consumes).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    """All of the user's settings as a ``{key: value}`` map."""

    values: dict[str, str | None]


class SettingsUpdate(BaseModel):
    """Request body for ``PUT /settings`` — upsert (merge) one or more settings.

    Only the keys present are written; keys not listed are left untouched. A key mapped
    to ``null`` is **removed** (finding S10), so a merge can clear a key, not only set
    one — previously a written key could never be deleted through the API. At least one
    key must be supplied.

    The typed numeric keys (``daily_*_limit`` and ``discover_count``) are bounds-checked
    server-side in the settings service, which also enforces
    ``daily_new_limit <= daily_total_limit`` (finding S9); a violation returns **422**.
    That check lives in the service, not this model, so the OpenAPI contract stays neutral.
    """

    values: dict[str, str | None] = Field(min_length=1)
