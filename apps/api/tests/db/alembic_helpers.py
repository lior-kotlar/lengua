"""Helpers for the Alembic migration tests (task 1.4) — not a test module itself.

The round-trip (1.4.2/1.4.3) and dev-seed (1.4.4) verifies must run against an **empty**
database, never the live Supabase ``public`` schema (which already carries the app tables from
the Supabase migration). So :func:`throwaway_database` creates a uniquely-named database on the
same server, yields its URL, and drops it at teardown; :func:`run_alembic` drives the real
``alembic`` CLI against it (a faithful automation of the literal ``alembic upgrade head`` /
``downgrade base`` verify commands).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import urllib.parse
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg

from tests.conftest import database_url

# apps/api — the working directory the alembic CLI runs from (finds alembic.ini + migrations/).
APPS_API = Path(__file__).resolve().parents[2]


def _swap_database(url: str, dbname: str) -> str:
    """Return ``url`` with its database name replaced by ``dbname`` (host/credentials kept)."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=f"/{dbname}"))


def run_alembic(target_url: str, *args: str) -> None:
    """Run ``alembic <args>`` against ``target_url`` from ``apps/api``; raise on a non-zero exit.

    Uses a subprocess (``python -m alembic``) so each invocation gets a fresh process — closing
    its asyncpg connections on exit, which keeps the throwaway database droppable — and mirrors
    the literal CLI verify commands exactly.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=APPS_API,
        env={**os.environ, "DATABASE_URL": target_url},
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`alembic {' '.join(args)}` failed (exit {proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )


@contextlib.contextmanager
def throwaway_database() -> Iterator[str]:
    """Create a uniquely-named empty database, yield its URL, and drop it at teardown."""
    admin_url = database_url()
    name = f"lengua_alembic_test_{uuid.uuid4().hex[:16]}"
    target_url = _swap_database(admin_url, name)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        yield target_url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@contextlib.contextmanager
def throwaway_database_with_auth() -> Iterator[str]:
    """A throwaway database pre-seeded with a minimal ``auth.users`` table.

    The 2.5.1 ``handle_new_user`` trigger fires ``after insert on auth.users`` — a table that only
    exists on a Supabase database. To exercise the *Alembic*-created trigger end-to-end on a
    throwaway Postgres, we first stand up a minimal stand-in (``id uuid`` is all the trigger reads),
    then the migrations run against a DB where ``to_regclass('auth.users')`` resolves, so the
    guarded trigger is actually created. Inserting into this table then fires it.
    """
    with throwaway_database() as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS auth")
            conn.execute(
                "CREATE TABLE auth.users ("
                "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
                "  email text"
                ")"
            )
        yield url


# A minimal stand-in for Supabase's ``auth.uid()`` (same body as the real one), so the RLS
# migration's ``auth.uid()``-referencing policies can be created on a throwaway Postgres.
_CREATE_AUTH_UID = """
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
  )::uuid
$$;
"""


@contextlib.contextmanager
def throwaway_database_with_auth_uid() -> Iterator[str]:
    """A throwaway database with both ``auth.users`` *and* an ``auth.uid()`` shim.

    The 2.6.1 RLS migration's owner policies reference ``auth.uid()`` (a Supabase-only function), so
    to apply that migration on a throwaway Postgres we add a faithful ``auth.uid()`` stand-in (it
    reads ``request.jwt.claims`` exactly like the real one). With it present,
    ``to_regprocedure('auth.uid()')`` resolves and the guarded migration creates the policies — so
    the structural assertions (RLS enabled + an owner policy per table) can run off the Supabase
    stack. Builds on :func:`throwaway_database_with_auth` so the 0002 trigger also applies.
    """
    with throwaway_database_with_auth() as url:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(_CREATE_AUTH_UID)
        yield url


def public_tables(url: str) -> set[str]:
    """The set of table names in the ``public`` schema of ``url``."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {row[0] for row in rows}


def public_indexes(url: str, table: str) -> set[str]:
    """The set of index names on ``public.<table>`` in ``url``."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def column_names(url: str, table: str) -> set[str]:
    """The set of column names on ``public.<table>`` in ``url``."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


def primary_key_columns(url: str, table: str) -> list[str]:
    """The ordered list of primary-key column names of ``public.<table>`` in ``url``."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT a.attname "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey) "
            "WHERE n.nspname = 'public' AND c.relname = %s AND i.indisprimary "
            "ORDER BY array_position(i.indkey, a.attnum)",
            (table,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def foreign_keys(url: str, table: str) -> list[tuple[str, str, str, str]]:
    """FKs of ``public.<table>`` as ``(column, ref_table, ref_column, delete_rule)`` tuples."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT kcu.column_name, ccu.table_name, ccu.column_name, rc.delete_rule "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name = tc.constraint_name "
            "  AND kcu.table_schema = tc.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "  AND ccu.table_schema = tc.table_schema "
            "JOIN information_schema.referential_constraints rc "
            "  ON rc.constraint_name = tc.constraint_name "
            "  AND rc.constraint_schema = tc.table_schema "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema = 'public' AND tc.table_name = %s",
            (table,),
        ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]


def public_functions(url: str) -> set[str]:
    """The set of function names in the ``public`` schema of ``url``."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT p.proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public'"
        ).fetchall()
    return {str(row[0]) for row in rows}
