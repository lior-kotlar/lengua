"""Lockstep regression — Alembic 0007 actually locks down ``prompt_versions`` (SECURITY, #80).

Like ``test_feature_flags_privileges.py`` for 0005, nothing else exercises 0007's role REVOKEs
against a role-bearing database: a *bare* Postgres no-ops them (the ``to_regrole`` guards) and the
live Supabase stack is built from the canonical SQL, not Alembic. So a typo in 0007's ``DO`` block
would pass CI silently.

This pins the Alembic side to the intended outcome on a throwaway DB that has the Supabase roles +
their default table privileges (so the REVOKEs have something real to strip): after
``alembic upgrade head`` the global ``prompt_versions`` table is created, seeded (one active version
per key), has RLS enabled with no policy, and ``authenticated`` / ``anon`` hold **no** privilege on
it; the upgrade/downgrade round-trip drops and recreates it cleanly.
"""

from __future__ import annotations

import psycopg
import pytest

from lengua_core import prompts
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
# the client roles — which 0007's REVOKE must then strip. Without this a fresh table grants them
# nothing anyway, so the REVOKE would be a vacuous no-op and the test wouldn't prove anything.
_SUPABASE_DEFAULT_GRANTS = (
    "alter default privileges in schema public grant all on tables to authenticated, anon"
)


def test_alembic_0007_locks_down_prompt_versions() -> None:
    """After ``alembic upgrade head``: prompt_versions exists, deny-by-default RLS, no grants."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "0006")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_ENSURE_ROLES)
            conn.execute(_SUPABASE_DEFAULT_GRANTS)

        run_alembic(url, "upgrade", "head")  # applies 0007 (create + seed + REVOKE + enable RLS)

        assert "prompt_versions" in public_tables(url)
        with psycopg.connect(url, autocommit=True) as conn:
            assert rls_status(conn).get("prompt_versions") is True, "RLS must be enabled"
            assert not policies_by_table(conn).get("prompt_versions"), "no policy (deny-by-default)"
            missing = [
                f"{role}:{priv}"
                for role in ("authenticated", "anon")
                for priv in _TABLE_PRIVILEGES
                if has_table_privilege(conn, role, "prompt_versions", priv)
            ]
        assert not missing, f"client roles still hold privileges on prompt_versions: {missing}"


def test_alembic_0007_seeds_one_active_version_per_key() -> None:
    """The 0007 upgrade seeds one active version (v1) per key, matching the code defaults."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        with psycopg.connect(url, autocommit=True) as conn:
            rows = conn.execute(
                "SELECT key, version, content FROM prompt_versions WHERE is_active"
            ).fetchall()
        active = {str(r[0]): (int(r[1]), str(r[2])) for r in rows}
    assert set(active) == set(prompts.PROMPT_KEYS)
    for key in prompts.PROMPT_KEYS:
        version, content = active[key]
        assert version == 1
        assert content == prompts.CODE_DEFAULTS[key], f"{key} seed drifted from the code default"


def test_alembic_0007_downgrade_is_reversible() -> None:
    """``downgrade 0006`` drops prompt_versions; re-``upgrade head`` recreates + reseeds it."""
    with throwaway_database_with_auth_uid() as url:
        run_alembic(url, "upgrade", "head")
        assert "prompt_versions" in public_tables(url)

        run_alembic(url, "downgrade", "0006")
        assert "prompt_versions" not in public_tables(url)

        run_alembic(url, "upgrade", "head")
        assert "prompt_versions" in public_tables(url)
