"""Alembic first-migration round-trip + schema tests (tasks 1.4.2, 1.4.3).

All run against a fresh throwaway database (never the live Supabase ``public`` schema). They
assert the migration builds the full schema, that an ``upgrade → downgrade → upgrade`` round-trip
succeeds, and that the migration carries no drift versus the ORM ``Base.metadata``.
"""

from __future__ import annotations

import pytest

from app.db import Base
from tests.db.alembic_helpers import (
    column_names,
    public_indexes,
    public_tables,
    run_alembic,
    throwaway_database,
)

pytestmark = pytest.mark.integration

# The eight tables the migration owns (the 6 app tables + the 2 cost-guard tables).
APP_TABLES = {
    "profiles",
    "languages",
    "cards",
    "reviews",
    "proficiency",
    "user_settings",
    "llm_usage",
    "llm_budget",
}


def test_upgrade_head_creates_full_schema() -> None:
    """`alembic upgrade head` creates every table (with the right columns), the cards lookup
    index, and both cost-guard tables (1.4.2 schema + index, 1.4.3 llm tables)."""
    with throwaway_database() as url:
        run_alembic(url, "upgrade", "head")

        tables = public_tables(url)
        assert tables >= APP_TABLES, f"missing tables: {APP_TABLES - tables}"

        # Each table's columns match the ORM metadata exactly — locks the migration to the models.
        for name in APP_TABLES:
            assert column_names(url, name) == set(Base.metadata.tables[name].columns.keys()), (
                f"column mismatch on {name}"
            )

        # The (user_id, language_id, saved, due) lookup index from 1.4.2.
        assert "cards_user_lang_due" in public_indexes(url, "cards")

        # The cost-guard tables from 1.4.3 (provider-agnostic names per the committed schema).
        assert {"llm_usage", "llm_budget"} <= tables


def test_roundtrip_upgrade_downgrade_upgrade() -> None:
    """`upgrade head` → `downgrade base` → `upgrade head` all succeed and are reversible."""
    with throwaway_database() as url:
        run_alembic(url, "upgrade", "head")
        assert public_tables(url) >= APP_TABLES

        run_alembic(url, "downgrade", "base")
        remaining = APP_TABLES & public_tables(url)
        assert remaining == set(), f"downgrade left tables behind: {remaining}"

        run_alembic(url, "upgrade", "head")
        assert public_tables(url) >= APP_TABLES


def test_migration_has_no_drift_versus_orm() -> None:
    """`alembic check` finds no pending autogenerate ops — the migration equals the ORM schema."""
    with throwaway_database() as url:
        run_alembic(url, "upgrade", "head")
        run_alembic(url, "check")  # raises if the migration and Base.metadata disagree
