"""DTOs for the account-lifecycle endpoints (task 2.8).

``GET /account/export`` returns :class:`AccountExport` — a faithful JSON bundle of the
authenticated user's learning data: their profile, languages, cards, reviews, per-language
proficiency, and settings, for store-compliance data export (Apple/Google) and GDPR portability.
(It deliberately omits internal LLM-usage counters — ``llm_usage`` — and the auth email, which
lives in Supabase Auth, not the app schema.) Every sub-model mirrors a row of the canonical schema;
the bundle is assembled scoped to ``current_user`` by :class:`~app.services.account.ExportService`,
so it can only ever contain the caller's own rows.

``DELETE /account`` returns no body (``204``), so it needs no response DTO here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProfileExport(BaseModel):
    """The user's profile row (account ``plan`` + creation time)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan: str
    created_at: datetime


class LanguageExport(BaseModel):
    """One language the user studies."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str | None = None
    vowelized: bool
    created_at: datetime


class CardExport(BaseModel):
    """One flashcard, with its full scheduling/generation state preserved."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    language_id: int
    front: str
    back: str
    used_words: list[str] | None = None
    direction: str | None = None
    word_explanations: dict[str, Any] | None = None
    gen_level: float | None = None
    saved: bool
    fsrs_state: dict[str, Any] | None = None
    due: datetime | None = None
    created_at: datetime


class ReviewExport(BaseModel):
    """One grade event (FSRS rating 1..4) against a card."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    rating: int
    reviewed_at: datetime


class ProficiencyExport(BaseModel):
    """The user's continuous proficiency score for one language."""

    model_config = ConfigDict(from_attributes=True)

    language_id: int
    score: float
    updated_at: datetime


class AccountExport(BaseModel):
    """The complete export bundle for one user — everything owned by ``current_user``.

    ``profile`` is ``None`` only for a token-only identity whose ``profiles`` row does not exist
    yet (e.g. mid-trigger); a real signed-up user always has one.
    """

    profile: ProfileExport | None = None
    languages: list[LanguageExport]
    cards: list[CardExport]
    reviews: list[ReviewExport]
    proficiency: list[ProficiencyExport]
    settings: dict[str, str | None]
