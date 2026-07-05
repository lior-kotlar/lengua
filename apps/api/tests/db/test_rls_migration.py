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

import re
from pathlib import Path

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

        # The global budget table is under deny-by-default RLS (enabled, no policy) as of 0004 —
        # a second lock on the kill-switch; it has no per-user *owner* policy.
        assert status.get(GLOBAL_TABLE) is True, (
            "llm_budget must have RLS enabled (deny-by-default)"
        )
        assert GLOBAL_TABLE not in policies, "llm_budget must have no policy"


# ── Canonical owner-policy predicates (parsed, not hard-coded) ─────────────────
# The Alembic 0003 migration reproduces the RLS section of the canonical Supabase SQL; parse the
# expected owner predicates from that file so this test tracks the source of record instead of
# duplicating literal strings (a drift between the two then fails loudly).
_CANONICAL_RLS_SQL = (
    Path(__file__).resolve().parents[4]
    / "supabase"
    / "migrations"
    / "20260621000000_initial_schema.sql"
)

# create policy <name> on <table> using (<col> = auth.uid()) [with check (...)]
_OWNER_POLICY_RE = re.compile(
    r"create\s+policy\s+\w+\s+on\s+(?P<table>\w+)\s+using\s*\(\s*"
    r"(?P<col>\w+)\s*=\s*auth\.uid\(\)\s*\)",
    re.IGNORECASE,
)


def _canonical_owner_predicates() -> dict[str, tuple[str, str]]:
    """``{table: (qual, with_check)}`` owner predicates parsed from the canonical Supabase SQL.

    Postgres deparses ``using (<col> = auth.uid())`` back as ``(<col> = auth.uid())`` in
    ``pg_policies.qual`` / ``.with_check``, so the expected value is reconstructed from the parsed
    owner column (``id`` for ``profiles``, ``user_id`` elsewhere) rather than string-matched against
    the raw SQL, whose spacing differs.
    """
    sql = _CANONICAL_RLS_SQL.read_text(encoding="utf-8")
    return {
        m.group("table"): (
            f"({m.group('col')} = auth.uid())",
            f"({m.group('col')} = auth.uid())",
        )
        for m in _OWNER_POLICY_RE.finditer(sql)
    }


def test_owner_policy_predicates_match_canonical() -> None:
    """Each owner policy uses ``auth.uid()`` on the right column, matching the canonical SQL.

    Parses the expected per-table predicates from the canonical Supabase RLS SQL (the source of
    record) instead of hard-coding them, so a change to a canonical owner column is tracked and a
    drift between it and the Alembic migration fails loudly.
    """
    expected = _canonical_owner_predicates()
    # The canonical file must define an owner policy for exactly the seven per-user tables.
    assert set(expected) == set(RLS_USER_TABLES), (
        f"canonical owner policies {sorted(expected)} != {sorted(RLS_USER_TABLES)}"
    )

    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        with psycopg.connect(url, autocommit=True) as conn:
            rows = conn.execute(
                "SELECT tablename, qual, with_check FROM pg_policies "
                "WHERE schemaname = 'public' ORDER BY tablename"
            ).fetchall()

    predicates = {str(t): (str(q), str(w)) for t, q, w in rows}
    for table, expected_pred in expected.items():
        assert predicates.get(table) == expected_pred, (
            table,
            predicates.get(table),
            expected_pred,
        )
    # The migration adds no owner policy the canonical SQL doesn't define.
    assert set(predicates) == set(expected)


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
