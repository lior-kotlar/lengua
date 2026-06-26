"""RLS coverage regression — every user-owned table is protected *and grantable* (task 2.6.4).

Two distinct regressions are guarded here:

* **Policy coverage.** A future table that carries a ``user_id`` column but forgets
  ``ENABLE ROW LEVEL SECURITY`` + an owner policy would silently leak across tenants. We query
  ``pg_class`` / ``pg_policies`` on the live schema and fail if **any** ``user_id``-bearing public
  table lacks ``relrowsecurity = true`` and at least one policy.
* **Grant coverage.** RLS only governs *which rows* a role may touch — the non-privileged
  ``authenticated`` role still needs the underlying table/sequence privileges to touch any row at
  all. Supabase grants these by default, but that is an *implicit* dependency: a future table
  created without the default grants (or a revoked grant / a sequence the role can't advance) would
  leave the policy in place yet make the first authenticated read/write fail with ``permission
  denied`` — green in CI, 500 in prod. We assert the grants explicitly via ``has_table_privilege``
  and ``has_sequence_privilege`` so that gap reds CI instead.

``profiles`` (owner-keyed on its PK ``id``, not ``user_id``) is asserted explicitly, and the
global ``llm_budget`` table is asserted to remain *un*protected on purpose (only the service role
writes it) so the exception is documented rather than accidental.
"""

from __future__ import annotations

import psycopg
import pytest

from app.db.rls import AUTHENTICATED_ROLE
from tests.conftest import database_url
from tests.rls_helpers import (
    GLOBAL_TABLE,
    INTEGER_PK_TABLES,
    RLS_USER_TABLES,
    has_sequence_privilege,
    has_table_privilege,
    identity_sequence,
    policies_by_table,
    rls_status,
    user_id_tables,
)

pytestmark = pytest.mark.integration

#: The privileges the ``authenticated`` role must hold on every RLS table for end-user CRUD to work
#: beneath the policies. Supabase grants all four (``GRANT ALL``); pinning them turns the implicit
#: dependency into a check that fails loudly if a table is ever created/altered without them.
REQUIRED_TABLE_PRIVILEGES: tuple[str, ...] = ("SELECT", "INSERT", "UPDATE", "DELETE")

#: ``llm_usage`` is the exception: group 3.1 revokes its writes from ``authenticated`` (writes go
#: through the privileged ``increment_llm_usage`` function), keeping only SELECT for the RLS-scoped
#: per-user count read. So we require only SELECT there, not full CRUD.
SELECT_ONLY_TABLES: frozenset[str] = frozenset({"llm_usage"})


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


def test_global_budget_table_is_deny_by_default() -> None:
    """``llm_budget`` has RLS enabled with **no** policy (deny-by-default) — not an owner policy.

    It is not a per-user table (no owner policy), but as of group 3.1 it is the global kill-switch:
    RLS is enabled with zero policies as a second lock (a stray future ``GRANT`` can't re-expose
    it), and only the privileged owner / SECURITY DEFINER functions (which bypass RLS) touch it.
    """
    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
    assert status.get(GLOBAL_TABLE) is True, "llm_budget must have RLS enabled (deny-by-default)"
    assert not policies.get(GLOBAL_TABLE), "llm_budget must have NO policy (deny-all)"


def test_authenticated_role_has_crud_grants_on_every_rls_table() -> None:
    """The ``authenticated`` role is actually GRANTed CRUD on every RLS table (SELECT-only on
    ``llm_usage``, whose writes are revoked in 3.1).

    A policy without the underlying grant is a trap: the table looks protected but the first
    authenticated query fails with ``permission denied``. Asserting the grant surface explicitly
    means a user table created/altered without it reds CI rather than 500ing the first prod write.
    ``llm_usage`` is the deliberate exception — only SELECT is required there; if it ever regained a
    write grant, ``test_killswitch_role_privileges_locked_down`` (in ``test_rls.py``) would red.
    """
    with psycopg.connect(database_url(), autocommit=True) as conn:
        missing: list[str] = []
        for table in RLS_USER_TABLES:
            required = ("SELECT",) if table in SELECT_ONLY_TABLES else REQUIRED_TABLE_PRIVILEGES
            missing.extend(
                f"{table}:{privilege}"
                for privilege in required
                if not has_table_privilege(conn, AUTHENTICATED_ROLE, table, privilege)
            )
    assert not sorted(missing), f"authenticated role is missing required table grants: {missing}"


def test_authenticated_role_can_use_the_identity_sequences() -> None:
    """``authenticated`` can advance every integer identity sequence (else INSERTs would fail).

    ``languages``/``cards``/``reviews`` use ``GENERATED ALWAYS AS IDENTITY``; an INSERT advances the
    backing sequence, which requires ``USAGE`` on it. Without that grant an authenticated INSERT
    fails even with a table INSERT grant and a satisfied ``WITH CHECK`` — exactly the silent gap the
    real-write round-trip (``test_rls_session.py``) would hit and this check pins as an invariant.
    """
    with psycopg.connect(database_url(), autocommit=True) as conn:
        problems: list[str] = []
        for table in INTEGER_PK_TABLES:
            sequence = identity_sequence(conn, table)
            if sequence is None:
                problems.append(f"{table}: no identity sequence found")
                continue
            if not has_sequence_privilege(conn, AUTHENTICATED_ROLE, sequence, "USAGE"):
                problems.append(f"{sequence}: USAGE not granted")
    assert not problems, f"authenticated role cannot use identity sequences: {problems}"
