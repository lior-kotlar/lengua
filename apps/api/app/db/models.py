"""SQLAlchemy 2.0 typed ORM models for the Lengua schema (task 1.3.2).

These mirror the canonical Postgres schema in
``supabase/migrations/20260621000000_initial_schema.sql`` exactly — same tables, column types
(``uuid`` / ``timestamptz`` / ``jsonb`` / ``real`` / ``bigint generated always as identity``),
foreign keys (all ``ON DELETE CASCADE``), per-user uniqueness, primary keys, and the ``cards``
lookup index — with one deliberate Phase-1 difference: ``profiles.id`` is a plain ``uuid``
primary key with **no** ``auth.users`` foreign key. Phase 1 runs against bare Postgres; the
``auth.users`` FK, the RLS policies, and the ``handle_new_user`` trigger are Supabase / Phase-2
concerns owned by the ``supabase/migrations`` SQL, not by the ORM.

Models live under ``app/`` so they sit inside the mypy ``--strict`` + ruff + coverage gate;
``lengua_core`` stays DB-agnostic and never imports SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Profile(Base):
    """A user's app-level profile.

    ``id`` mirrors the Supabase ``auth.users`` id but carries no FK in Phase 1 (bare Postgres).
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'free'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Language(Base):
    """A language a user studies. Unique per user by ``name`` (was a global unique in SQLite)."""

    __tablename__ = "languages"
    __table_args__ = (UniqueConstraint("user_id", "name", name="languages_user_id_name_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text)
    vowelized: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Card(Base):
    """A single flashcard (one direction); a sentence yields a recognition + production pair."""

    __tablename__ = "cards"
    __table_args__ = (Index("cards_user_lang_due", "user_id", "language_id", "saved", "due"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("languages.id", ondelete="CASCADE"), nullable=False
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    used_words: Mapped[list[str] | None] = mapped_column(JSONB)
    direction: Mapped[str | None] = mapped_column(Text)  # 'recognition' | 'production'
    word_explanations: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    gen_level: Mapped[float | None] = mapped_column(REAL)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fsrs_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Review(Base):
    """A grade event for a card (FSRS rating 1..4). ``user_id`` is denormalized for scoping/RLS."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=Again .. 4=Easy
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Proficiency(Base):
    """Per-user, per-language proficiency score. Composite PK ``(user_id, language_id)``."""

    __tablename__ = "proficiency"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    language_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("languages.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(REAL, nullable=False, server_default=text("0.0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserSettings(Base):
    """Per-user key/value preferences. Composite PK ``(user_id, key)``."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)


class LlmUsage(Base):
    """Per-user, per-day, per-kind LLM call counter for the cost guard (Phase 3).

    Provider-agnostic (the historical ``gemini_*`` names were superseded by ``llm_*`` in the
    committed schema). Composite PK ``(user_id, day, kind)``.
    """

    __tablename__ = "llm_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)  # 'generate' | 'discover' | 'explain'
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class LlmBudget(Base):
    """Project-wide daily LLM budget kill-switch (global; no per-user RLS). PK ``day``."""

    __tablename__ = "llm_budget"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class FeatureFlag(Base):
    """A global feature-flag override row (task 6.9).

    GLOBAL operator config — **not** per-user data: a present row overrides the env default for the
    flag of that ``name`` for *everyone*, so a risky/new feature can be toggled in prod without a
    redeploy. Absence of a row means "fall back to the env default" (off unless ``FEATURE_*`` set).
    Like ``llm_budget`` it is locked down to the server — ``REVOKE``\\d from ``authenticated`` /
    ``anon`` and under deny-by-default RLS (Alembic 0005 / the canonical Supabase SQL) — so a user
    can never enable their own flags: writes are admin/service-role only, reads happen server-side
    and reach clients only via the public ``GET /feature-flags`` endpoint. PK ``name``.
    """

    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
