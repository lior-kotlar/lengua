"""RLS coverage regression — every user-owned table is protected (task 2.6.4).

A future table that carries a ``user_id`` column but forgets ``ENABLE ROW LEVEL SECURITY`` + an
owner policy would silently leak across tenants. This test queries ``pg_class`` / ``pg_policies``
on the live schema and fails if **any** ``user_id``-bearing public table lacks
``relrowsecurity = true`` and at least one policy — so the omission is caught in CI, not in prod.

``profiles`` (owner-keyed on its PK ``id``, not ``user_id``) is asserted explicitly, and the
global ``llm_budget`` table is asserted to remain *un*protected on purpose (only the service role
writes it) so the exception is documented rather than accidental.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.conftest import database_url
from tests.rls_helpers import (
    GLOBAL_TABLE,
    RLS_USER_TABLES,
    policies_by_table,
    rls_status,
    user_id_tables,
)

pytestmark = pytest.mark.integration


def test_every_user_id_table_has_rls_and_a_policy() -> None:
    """Each public base table with a ``user_id`` column has RLS enabled + an owner policy."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
        scoped_tables = user_id_tables(conn)

    # Guard against a vacuous pass: the known user_id tables must actually be discovered.
    expected = set(RLS_USER_TABLES) - {"profiles"}  # profiles is keyed on id, not user_id
    assert expected <= scoped_tables, f"introspection missed tables: {expected - scoped_tables}"

    missing_rls = sorted(t for t in scoped_tables if not status.get(t))
    assert not missing_rls, f"tables with a user_id column but RLS disabled: {missing_rls}"

    missing_policy = sorted(t for t in scoped_tables if not policies.get(t))
    assert not missing_policy, f"tables with a user_id column but no RLS policy: {missing_policy}"


def test_profiles_is_protected_via_its_id() -> None:
    """``profiles`` is a user table too — protected, even though it has no ``user_id`` column."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
    assert status.get("profiles") is True, "RLS must be enabled on profiles"
    assert policies.get("profiles"), "profiles must have an owner policy"


def test_global_budget_table_is_intentionally_unprotected() -> None:
    """``llm_budget`` stays global (no RLS): a deliberate, documented exception."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
    assert status.get(GLOBAL_TABLE) is False, "llm_budget must remain global (no RLS)"
    assert not policies.get(GLOBAL_TABLE), "llm_budget must have no policies"
