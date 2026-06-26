"""Usage-accounting tables + kill-switch migration round-trip (tasks 3.1.1 / 3.1.2 / 3.1.3).

These run against a fresh throwaway database (never the live Supabase ``public`` schema). They
confirm the Phase-1 cost-guard tables (``llm_usage`` / ``llm_budget``) carry the right columns,
primary keys, and the ``ON DELETE CASCADE`` FK from ``llm_usage.user_id`` → ``profiles.id``, and
that the Phase-3 kill-switch migration (0004) creates its ``SECURITY DEFINER`` functions and
round-trips cleanly (``alembic downgrade -1`` → ``upgrade head``).

The throwaway DB is built with an ``auth.uid()`` shim so the 0003 RLS migration also applies; the
0004 role grants/revokes are guarded on ``to_regrole(...)`` and simply no-op there (the throwaway
has no ``authenticated``/``anon``/``service_role`` roles) — the *live*-stack privilege model is
proven separately in ``tests/test_rls.py``.
"""

from __future__ import annotations

import pytest

from tests.db.alembic_helpers import (
    column_names,
    foreign_keys,
    primary_key_columns,
    public_functions,
    public_tables,
    run_alembic,
    throwaway_database_with_auth_uid,
)

pytestmark = pytest.mark.integration

# The two SECURITY DEFINER functions migration 0004 adds.
_KILLSWITCH_FUNCTIONS = {"increment_llm_usage", "get_llm_budget_count"}


def test_usage_tables_columns_and_pks() -> None:
    """``llm_usage`` / ``llm_budget`` have the documented columns + composite/PKs after upgrade."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")

        tables = public_tables(url)
        assert {"llm_usage", "llm_budget"} <= tables

        assert column_names(url, "llm_usage") == {"user_id", "day", "kind", "count"}
        assert column_names(url, "llm_budget") == {"day", "count"}

        # Composite PK on (user_id, day, kind); single-column PK on (day).
        assert primary_key_columns(url, "llm_usage") == ["user_id", "day", "kind"]
        assert primary_key_columns(url, "llm_budget") == ["day"]


def test_llm_usage_user_id_cascade_fk() -> None:
    """``llm_usage.user_id`` is an ``ON DELETE CASCADE`` FK to ``profiles.id`` (deleting the user
    removes their usage rows); ``llm_budget`` has no FK (it is global)."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")

        fks = foreign_keys(url, "llm_usage")
        assert ("user_id", "profiles", "id", "CASCADE") in fks, fks
        assert foreign_keys(url, "llm_budget") == []


def test_killswitch_functions_created() -> None:
    """Migration 0004 creates both ``SECURITY DEFINER`` cost-guard functions."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        assert public_functions(url) >= _KILLSWITCH_FUNCTIONS


def test_migration_0004_round_trips() -> None:
    """``upgrade head`` → ``downgrade -1`` (0003) → ``upgrade head`` (0004) is reversible.

    After the down-step the kill-switch functions are gone; after re-upgrading they exist again,
    proving 0004 is a clean, reversible head migration.
    """
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        assert public_functions(url) >= _KILLSWITCH_FUNCTIONS

        run_alembic(url, "downgrade", "-1")  # 0004 → 0003: functions dropped
        assert public_functions(url).isdisjoint(_KILLSWITCH_FUNCTIONS)
        # The tables themselves survive the down-step (they belong to 0001).
        assert {"llm_usage", "llm_budget"} <= public_tables(url)

        run_alembic(url, "upgrade", "head")  # back to 0004: functions recreated
        assert public_functions(url) >= _KILLSWITCH_FUNCTIONS
