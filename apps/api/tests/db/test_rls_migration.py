"""Alembic RLS migration (task 2.6.1).

The new revision ``0003`` reproduces the canonical Supabase RLS section: it enables Row-Level
Security and creates an owner policy on each of the seven per-user tables, while leaving
``llm_budget`` global. These tests run it against throwaway databases (never the live ``public``
schema) and assert the structural outcome the task's ``verify`` calls for:

* on a database where ``auth.uid()`` exists, ``alembic upgrade head`` enables RLS
  (``pg_class.relrowsecurity = true``) on every user table and ``pg_policies`` lists the owner
  policy per table; the migration is reversible; and
* on a **bare** Postgres (no ``auth.uid()``) the migration is a clean no-op, so the existing
  schema round-trip / ``alembic check`` keep working — RLS stays a Supabase concern.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.db.alembic_helpers import (
    run_alembic,
    throwaway_database,
    throwaway_database_with_auth_uid,
)
from tests.rls_helpers import (
    GLOBAL_TABLE,
    RLS_USER_TABLES,
    policies_by_table,
    rls_status,
)

pytestmark = pytest.mark.integration


def test_upgrade_enables_rls_and_owner_policies() -> None:
    """`alembic upgrade head` turns on RLS + an owner policy for every user table (and only those).

    Automates the literal 2.6.1 verify: ``relrowsecurity = true`` for each user table and a
    matching ``<table>_owner`` policy in ``pg_policies``; ``llm_budget`` stays global.
    """
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")

        with psycopg.connect(url, autocommit=True) as conn:
            status = rls_status(conn)
            policies = policies_by_table(conn)

        for table in RLS_USER_TABLES:
            assert status.get(table) is True, f"RLS not enabled on {table}"
            assert f"{table}_owner" in policies.get(table, []), f"no owner policy on {table}"

        # The global budget table is deliberately NOT protected.
        assert status.get(GLOBAL_TABLE) is False, "llm_budget must stay global (no RLS)"
        assert GLOBAL_TABLE not in policies


def test_owner_policy_predicates_match_canonical() -> None:
    """Each owner policy uses ``auth.uid()`` on the right column (``profiles.id`` vs ``user_id``).

    Keeps the Alembic migration byte-for-byte consistent with the canonical Supabase SQL.
    """
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        with psycopg.connect(url, autocommit=True) as conn:
            rows = conn.execute(
                "SELECT tablename, qual, with_check FROM pg_policies "
                "WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()

    predicates = {str(t): (str(q), str(w)) for t, q, w in rows}
    assert predicates["profiles"] == ("(id = auth.uid())", "(id = auth.uid())")
    for table in ("languages", "cards", "reviews", "proficiency", "user_settings", "llm_usage"):
        assert predicates[table] == ("(user_id = auth.uid())", "(user_id = auth.uid())"), table


def test_downgrade_removes_rls_and_is_reversible() -> None:
    """`downgrade` drops the policies + disables RLS; re-`upgrade` restores them (round trip)."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        run_alembic(url, "downgrade", "0002")  # undo only the RLS revision

        with psycopg.connect(url, autocommit=True) as conn:
            status = rls_status(conn)
            policies = policies_by_table(conn)
        for table in RLS_USER_TABLES:
            assert status.get(table) is False, f"RLS still enabled on {table} after downgrade"
            assert table not in policies, f"policy left behind on {table}"

        # Re-applying restores RLS on every user table (proves the round-trip is clean).
        run_alembic(url, "upgrade", "head")
        with psycopg.connect(url, autocommit=True) as conn:
            status = rls_status(conn)
        for table in RLS_USER_TABLES:
            assert status.get(table) is True, f"RLS not restored on {table} after re-upgrade"


def test_migration_is_noop_on_bare_postgres() -> None:
    """Without ``auth.uid()`` the migration applies but enables no RLS — keeps bare-DB CI green."""
    with throwaway_database() as url:  # no auth schema, no auth.uid()
        run_alembic(url, "upgrade", "head")  # must not raise despite the auth.uid() policies
        with psycopg.connect(url, autocommit=True) as conn:
            status = rls_status(conn)
            policies = policies_by_table(conn)
        for table in RLS_USER_TABLES:
            assert status.get(table) is False, f"RLS unexpectedly enabled on bare PG: {table}"
        assert policies == {}, f"no policies should exist on bare PG, found {policies}"
