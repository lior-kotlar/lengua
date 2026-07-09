"""Assert the ORM metadata matches the canonical Postgres schema (task 1.3.2).

Pure introspection of ``Base.metadata`` — no database needed, so this runs in the plain unit
suite. The source of truth is ``supabase/migrations/20260621000000_initial_schema.sql``; these
assertions lock the ORM to it (UUID / timestamptz / jsonb / real / bigint types, foreign keys
with ``ON DELETE CASCADE``, per-user uniqueness, primary keys, and the ``cards`` index), with the
one deliberate Phase-1 difference that ``profiles.id`` carries no ``auth.users`` foreign key.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    SmallInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import Base

METADATA = Base.metadata


def _assert_fk(column: Column[Any], table: str, *, ondelete: str = "CASCADE") -> None:
    """Assert ``column`` has exactly one FK to ``table.id`` with the given ON DELETE action."""
    fks = list(column.foreign_keys)
    assert len(fks) == 1, f"{column} should have exactly one FK"
    fk = fks[0]
    assert fk.column.table.name == table
    assert fk.ondelete == ondelete


def test_all_expected_tables_present() -> None:
    assert set(METADATA.tables) == {
        "profiles",
        "languages",
        "cards",
        "reviews",
        "proficiency",
        "user_settings",
        "llm_usage",
        "llm_budget",
        "feature_flags",
        "prompt_versions",
    }


def test_feature_flags_is_global_name_pk_table() -> None:
    """``feature_flags`` (task 6.9) is global config: a ``name`` text PK + ``enabled`` +
    ``updated_at``, no per-user ``user_id`` (owner/server config, locked down like llm_budget)."""
    feature_flags = METADATA.tables["feature_flags"]
    assert list(feature_flags.primary_key.columns.keys()) == ["name"]
    assert isinstance(feature_flags.c["enabled"].type, Boolean)
    assert feature_flags.c["enabled"].nullable is False
    assert isinstance(feature_flags.c["updated_at"].type, DateTime)
    assert "user_id" not in feature_flags.c


def test_prompt_versions_is_global_versioned_table() -> None:
    """``prompt_versions`` (#80) is global config: a uuid PK, ``(key, version)`` unique, an active
    partial-unique index, ``content`` text, and no per-user ``user_id`` (owner/server config)."""
    pv = METADATA.tables["prompt_versions"]
    assert list(pv.primary_key.columns.keys()) == ["id"]
    assert isinstance(pv.c["id"].type, UUID)
    assert isinstance(pv.c["version"].type, Integer)
    assert pv.c["content"].nullable is False
    assert pv.c["is_active"].nullable is False
    assert isinstance(pv.c["is_active"].type, Boolean)
    assert "user_id" not in pv.c
    # UNIQUE (key, version) keeps versions monotonic per key.
    key_version_uniques = [
        tuple(c.name for c in con.columns)
        for con in pv.constraints
        if isinstance(con, UniqueConstraint)
    ]
    assert ("key", "version") in key_version_uniques
    # Partial unique index enforces at most one active version per key.
    active_indexes = [ix for ix in pv.indexes if ix.name == "prompt_versions_one_active_per_key"]
    assert len(active_indexes) == 1
    assert active_indexes[0].unique is True
    assert [c.name for c in active_indexes[0].columns] == ["key"]


def test_profiles_id_is_uuid_pk_without_auth_fk() -> None:
    profiles = METADATA.tables["profiles"]
    id_col = profiles.c["id"]
    assert isinstance(id_col.type, UUID)
    assert id_col.primary_key is True
    # Phase 1 deliberately drops the auth.users FK (added back by the Supabase migration in P2).
    assert id_col.foreign_keys == set()
    created = profiles.c["created_at"]
    assert isinstance(created.type, DateTime)
    assert created.type.timezone is True


def test_languages_fk_unique_and_types() -> None:
    languages = METADATA.tables["languages"]
    assert isinstance(languages.c["id"].type, BigInteger)
    assert languages.c["id"].primary_key is True
    assert isinstance(languages.c["user_id"].type, UUID)
    _assert_fk(languages.c["user_id"], "profiles")
    assert isinstance(languages.c["vowelized"].type, Boolean)
    uniques = [c for c in languages.constraints if isinstance(c, UniqueConstraint)]
    assert any({col.name for col in u.columns} == {"user_id", "name"} for u in uniques)


def test_cards_types_fks_and_index() -> None:
    cards = METADATA.tables["cards"]
    assert isinstance(cards.c["id"].type, BigInteger)
    _assert_fk(cards.c["user_id"], "profiles")
    _assert_fk(cards.c["language_id"], "languages")
    assert isinstance(cards.c["used_words"].type, JSONB)
    assert isinstance(cards.c["word_explanations"].type, JSONB)
    assert isinstance(cards.c["fsrs_state"].type, JSONB)
    assert isinstance(cards.c["gen_level"].type, REAL)
    assert isinstance(cards.c["saved"].type, Boolean)
    due = cards.c["due"]
    assert isinstance(due.type, DateTime)
    assert due.type.timezone is True
    # The (user_id, language_id, saved, due) lookup index exists.
    matching = [
        i
        for i in cards.indexes
        if list(i.columns.keys()) == ["user_id", "language_id", "saved", "due"]
    ]
    assert len(matching) == 1


def test_reviews_fks_and_rating() -> None:
    reviews = METADATA.tables["reviews"]
    _assert_fk(reviews.c["user_id"], "profiles")
    _assert_fk(reviews.c["card_id"], "cards")
    assert isinstance(reviews.c["rating"].type, SmallInteger)
    assert isinstance(reviews.c["reviewed_at"].type, DateTime)
    assert reviews.c["reviewed_at"].type.timezone is True


def test_proficiency_composite_pk() -> None:
    proficiency = METADATA.tables["proficiency"]
    assert list(proficiency.primary_key.columns.keys()) == ["user_id", "language_id"]
    _assert_fk(proficiency.c["user_id"], "profiles")
    _assert_fk(proficiency.c["language_id"], "languages")
    assert isinstance(proficiency.c["score"].type, REAL)


def test_user_settings_composite_pk() -> None:
    user_settings = METADATA.tables["user_settings"]
    assert list(user_settings.primary_key.columns.keys()) == ["user_id", "key"]
    _assert_fk(user_settings.c["user_id"], "profiles")


def test_llm_usage_and_budget_pks() -> None:
    llm_usage = METADATA.tables["llm_usage"]
    assert list(llm_usage.primary_key.columns.keys()) == ["user_id", "day", "kind"]
    assert isinstance(llm_usage.c["day"].type, Date)
    assert isinstance(llm_usage.c["count"].type, Integer)
    _assert_fk(llm_usage.c["user_id"], "profiles")

    llm_budget = METADATA.tables["llm_budget"]
    assert list(llm_budget.primary_key.columns.keys()) == ["day"]
    assert isinstance(llm_budget.c["day"].type, Date)
