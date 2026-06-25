"""Language DTOs (task 1.5.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LanguageCreate(BaseModel):
    """Request body for ``POST /languages``."""

    name: str = Field(min_length=1)
    code: str | None = None
    vowelized: bool = False


class LanguageUpdate(BaseModel):
    """Request body for ``PATCH /languages/{id}`` — toggle the ``vowelized`` flag."""

    vowelized: bool


class LanguageOut(BaseModel):
    """A language as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str | None
    vowelized: bool
