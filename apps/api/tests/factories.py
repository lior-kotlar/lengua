"""Simple builders for the core domain entities, matching the Phase-1 DDL sketch
(see planning/03-backend.md).

The SQLAlchemy ORM models don't exist yet (Phase 1), so these are lightweight dataclass
builders that produce fully-populated, referentially-consistent entities for tests. When
the ORM lands, these can be swapped for DB-backed factories with the same call surface.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_language_ids = itertools.count(1)
_card_ids = itertools.count(1)
_review_ids = itertools.count(1)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class User:
    """An app user (mirrors the `profiles` row, PK = Supabase auth.users.id)."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    plan: str = "free"
    created_at: datetime = field(default_factory=_now)


@dataclass
class Language:
    user_id: uuid.UUID
    name: str = "Spanish"
    id: int = field(default_factory=lambda: next(_language_ids))
    code: str | None = "es"
    vowelized: bool = False
    created_at: datetime = field(default_factory=_now)


@dataclass
class Card:
    user_id: uuid.UUID
    language_id: int
    front: str = "El gato duerme."
    back: str = "The cat sleeps."
    id: int = field(default_factory=lambda: next(_card_ids))
    used_words: list[str] = field(default_factory=lambda: ["gato"])
    direction: str = "recognition"
    word_explanations: dict[str, str] = field(default_factory=dict)
    gen_level: float | None = None
    saved: bool = False
    fsrs_state: dict[str, object] | None = None
    due: datetime | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class Review:
    user_id: uuid.UUID
    card_id: int
    rating: int = 3  # 1=Again, 2=Hard, 3=Good, 4=Easy
    id: int = field(default_factory=lambda: next(_review_ids))
    reviewed_at: datetime = field(default_factory=_now)


def make_user(**overrides: Any) -> User:
    return User(**overrides)


def make_language(user: User | None = None, **overrides: Any) -> Language:
    user = user or make_user()
    overrides.setdefault("user_id", user.id)
    return Language(**overrides)


def make_card(language: Language | None = None, **overrides: Any) -> Card:
    language = language or make_language()
    overrides.setdefault("user_id", language.user_id)
    overrides.setdefault("language_id", language.id)
    return Card(**overrides)


def make_review(card: Card | None = None, **overrides: Any) -> Review:
    card = card or make_card()
    overrides.setdefault("user_id", card.user_id)
    overrides.setdefault("card_id", card.id)
    return Review(**overrides)
