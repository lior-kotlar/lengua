"""Language DTOs (task 1.5.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LanguageCreate(BaseModel):
    """Request body for ``POST /languages``."""

    name: str = Field(min_length=1)
    code: str | None = None
    vowelized: bool = False


class LanguageUpdate(BaseModel):
    """Request body for ``PATCH /languages/{id}`` — a partial update of the editable fields.

    Every field is optional; only the ones actually present in the request body are applied (the
    route reads ``model_dump(exclude_unset=True)``), so a client can rename a language, set or clear
    its ``code``, or toggle ``vowelized`` independently. ``code`` may be sent as ``null`` to clear
    it. Making ``name``/``code`` editable lets a user fix a mistyped name or a missing/blank code
    after creation — e.g. to give a right-to-left language its ``he``/``ar`` code so its script
    renders (direction + diacritic-correct font) correctly.
    """

    name: str | None = Field(default=None, min_length=1)
    code: str | None = None
    vowelized: bool | None = None


class LanguageOut(BaseModel):
    """A language as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str | None
    vowelized: bool


class LanguageCreateOut(LanguageOut):
    """``POST /languages`` response: the language plus whether THIS request created it.

    ``created`` is ``True`` when a new language was inserted and ``False`` when the name already
    existed — an idempotent add, where the existing row is returned **unchanged**. It lets the
    client tell a fresh add from a re-add, so re-adding an existing language never resets its
    recorded proficiency (finding S3). Returned with HTTP 200 (the API's convention for ``POST``),
    so the flag — not the status code — carries the created/existing signal.
    """

    created: bool
