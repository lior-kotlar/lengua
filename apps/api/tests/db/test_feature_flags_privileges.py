"""Lockstep regression — Alembic 0005 actually locks down ``feature_flags`` (SECURITY, task 6.9.1).

Like ``test_role_privileges.py`` for the kill-switch (0004), nothing else exercises 0005's role
REVOKEs against a role-bearing database: a *bare* Postgres no-ops them (the ``to_regrole`` guards)
and the live Supabase stack is built from the canonical SQL, not Alembic. So a typo in 0005's ``DO``
block would pass CI silently.

This pins the Alembic side to the intended outcome on a throwaway DB that has the Supabase roles +
their default table privileges (so the REVOKEs have something real to strip): after
``alembic upgrade head`` the global ``feature_flags`` table is created, has RLS enabled with no
policy, and ``authenticated`` / ``anon`` hold **no** privilege on it; the upgrade/downgrade
round-trip drops and recreates it cleanly.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.db.alembic_helpers import (
    public_tables,
    run_alembic,
    throwaway_database_with_auth_uid,
)
from tests.rls_helpers import has_table_privilege, policies_by_table, rls_status

pytestmark = pytest.mark.integration

_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")

# Ensure the two Supabase client roles exist (no-op on the real stack — they're cluster-global).
_ENSURE_ROLES = """
do $$
begin
  if to_regrole('authenticated') is null then create role authenticated; end if;
  if to_regrole('anon') is null then create role anon; end if;
end $$;
"""

# Mimic Supabase's default-privilege grant so a table CREATEd by the migration auto-grants CRUD to
# the client roles — which 0005's REVOKE must then strip. Without this a fresh table grants them
# nothing anyway, so the REVOKE would be a vacuous no-op and the test wouldn't prove anything.
_SUPABASE_DEFAULT_GRANTS = (
    "alter default privileges in schema public grant all on tables to authenticated, anon"
)


def test_alembic_0005_locks_down_feature_flags() -> None:
    """After ``alembic upgrade head``: feature_flags exists, deny-by-default RLS, no grants."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "0004")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_ENSURE_ROLES)
            conn.execute(_SUPABASE_DEFAULT_GRANTS)

        run_alembic(url, "upgrade", "head")  # applies 0005 (create + REVOKE + enable RLS)

        assert "feature_flags" in public_tables(url)
        with psycopg.connect(url, autocommit=True) as conn:
            assert rls_status(conn).get("feature_flags") is True, "RLS must be enabled"
            assert not policies_by_table(conn).get("feature_flags"), "no policy (deny-by-default)"
            missing = [
                f"{role}:{priv}"
                for role in ("authenticated", "anon")
                for priv in _TABLE_PRIVILEGES
                if has_table_privilege(conn, role, "feature_flags", priv)
            ]
        assert not missing, f"client roles still hold privileges on feature_flags: {missing}"


def test_alembic_0005_downgrade_is_reversible() -> None:
    """``downgrade 0004`` drops feature_flags; re-``upgrade head`` recreates it (round-trips)."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        assert "feature_flags" in public_tables(url)

        run_alembic(url, "downgrade", "0004")
        assert "feature_flags" not in public_tables(url)

        run_alembic(url, "upgrade", "head")
        assert "feature_flags" in public_tables(url)
