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
