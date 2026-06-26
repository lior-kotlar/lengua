"""Lockstep regression — the Alembic 0004 role REVOKE/GRANT statements actually take effect (F1).

Nothing else exercises the Alembic role grants/revokes against a role-bearing database: a *bare*
Postgres no-ops them (the ``to_regrole`` guards), and the live Supabase stack is built from the
canonical SQL, not Alembic. So a typo in 0004's ``DO`` block (e.g. revoking the wrong privilege, or
forgetting the ``service_role`` grant) would pass CI silently. This test pins the Alembic side to
the intended privilege outcome — keeping it in lockstep with the canonical SQL.

It runs against a throwaway database that has the Supabase roles (they are cluster-global on the
local stack; created here if somehow absent), pre-grants the Supabase-default CRUD so 0004's REVOKEs
have something real to remove, then asserts that after ``alembic upgrade head`` the non-privileged
roles are locked out and ``service_role`` can still EXECUTE the functions.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.db.alembic_helpers import run_alembic, throwaway_database_with_auth_uid
from tests.rls_helpers import has_function_privilege, has_table_privilege

pytestmark = pytest.mark.integration

_INCREMENT_SIG = "public.increment_llm_usage(uuid,text,date)"
_READER_SIG = "public.get_llm_budget_count(date)"

# Ensure the three Supabase roles exist (no-op on the real stack, where they are cluster-global).
_ENSURE_ROLES = """
do $$
begin
  if to_regrole('authenticated') is null then create role authenticated; end if;
  if to_regrole('anon') is null then create role anon; end if;
  if to_regrole('service_role') is null then create role service_role; end if;
end $$;
"""


def test_alembic_0004_locks_down_roles() -> None:
    """After ``alembic upgrade head``: authenticated/anon locked out, service_role keeps EXECUTE."""
    with throwaway_database_with_auth_uid() as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_ENSURE_ROLES)

        # Build up to (but not including) the kill-switch, then simulate the Supabase-default CRUD
        # grants so 0004's REVOKEs have real privileges to strip.
        run_alembic(url, "upgrade", "0003")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE llm_usage TO authenticated, anon"
            )
            conn.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE llm_budget TO authenticated, anon"
            )

        run_alembic(url, "upgrade", "head")  # applies 0004 (REVOKE/GRANT + deny-by-default RLS)

        with psycopg.connect(url) as conn:
            for role in ("authenticated", "anon"):
                # No EXECUTE on either SECURITY DEFINER function.
                assert not has_function_privilege(conn, role, _INCREMENT_SIG), f"{role}:exec:inc"
                assert not has_function_privilege(conn, role, _READER_SIG), f"{role}:exec:reader"
                # No privilege at all on the global kill-switch table.
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    assert not has_table_privilege(conn, role, "llm_budget", priv), (
                        f"{role}:b:{priv}"
                    )
                # No write on the per-user counter (writes go through the definer function only).
                for priv in ("INSERT", "UPDATE", "DELETE"):
                    assert not has_table_privilege(conn, role, "llm_usage", priv), (
                        f"{role}:u:{priv}"
                    )

            # authenticated keeps SELECT on llm_usage (the RLS-scoped per-user count read needs it).
            assert has_table_privilege(conn, "authenticated", "llm_usage", "SELECT")
            # service_role (the trusted server role) retains EXECUTE on both functions.
            assert has_function_privilege(conn, "service_role", _INCREMENT_SIG)
            assert has_function_privilege(conn, "service_role", _READER_SIG)
