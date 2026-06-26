"""Profiles-on-first-login bootstrap (task 2.5.1).

A ``profiles`` row (``plan='free'``) must exist for every user from their first login. The
canonical mechanism is the ``handle_new_user`` ``security definer`` function + the
``on_auth_user_created`` ``after insert`` trigger on ``auth.users`` — created by the new Alembic
revision ``0002`` (matching ``supabase/migrations/20260621000000_initial_schema.sql``). No app-side
write runs in the request path; the trigger fires once, at signup, inside GoTrue.

Two layers of proof, both ``@pytest.mark.integration`` (auto-skipped when the DB/Auth stack is
unreachable):

* **The Alembic migration itself** — ``alembic upgrade head`` against a throwaway Postgres that has
  a minimal ``auth.users`` creates a *working* trigger: inserting an auth user makes exactly one
  ``plan='free'`` profile, a second distinct signup gets its own, and neither is duplicated; the
  migration is reversible on that DB too.
* **The live Supabase flow** — a real admin-created (pre-confirmed) signup yields exactly one
  ``plan='free'`` profile (the trigger ran), and logging in again does **not** create a second row.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from tests.conftest import database_url
from tests.db.alembic_helpers import run_alembic, throwaway_database_with_auth
from tests.supabase_auth import create_confirmed_user, delete_user, login

pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────────────────────────


def _profiles_for(conn: psycopg.Connection, user_id: str | uuid.UUID) -> list[tuple[object, ...]]:
    return conn.execute("SELECT id, plan FROM profiles WHERE id = %s", (str(user_id),)).fetchall()


def _count_profiles_for(user_id: str | uuid.UUID) -> int:
    with psycopg.connect(database_url()) as conn:
        row = conn.execute(
            "SELECT count(*) FROM profiles WHERE id = %s", (str(user_id),)
        ).fetchone()
    assert row is not None
    return int(row[0])


# ── The Alembic migration creates a working trigger ──────────────────────────────────────────


def test_alembic_migration_creates_working_handle_new_user_trigger() -> None:
    """`alembic upgrade head` builds the function + trigger; an auth.users insert bootstraps the
    profile (``plan='free'``), distinct signups each get exactly one row, none are duplicated."""
    with throwaway_database_with_auth() as url:
        run_alembic(url, "upgrade", "head")

        with psycopg.connect(url, autocommit=True) as conn:
            # The security-definer function and the trigger both exist after the migration.
            fn = conn.execute("SELECT to_regprocedure('public.handle_new_user()')").fetchone()
            assert fn is not None and fn[0] is not None, "handle_new_user() was not created"
            trg = conn.execute(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgname = 'on_auth_user_created' AND NOT tgisinternal"
            ).fetchone()
            assert trg is not None, "on_auth_user_created trigger was not created on auth.users"

            # First signup → exactly one profile, plan defaults to 'free'.
            uid = uuid.uuid4()
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s)", (uid, "first@lengua.test")
            )
            rows = _profiles_for(conn, uid)
            assert len(rows) == 1, "trigger should create exactly one profile on signup"
            assert rows[0][1] == "free", "bootstrapped profile must default to plan='free'"

            # A second, distinct signup gets its own single profile; the first is untouched.
            uid2 = uuid.uuid4()
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s)", (uid2, "second@lengua.test")
            )
            assert len(_profiles_for(conn, uid2)) == 1
            assert len(_profiles_for(conn, uid)) == 1  # not duplicated by the second signup
            total = conn.execute("SELECT count(*) FROM profiles").fetchone()
            assert total is not None and total[0] == 2


def test_alembic_trigger_is_reversible() -> None:
    """`downgrade base` drops the trigger + function cleanly and `upgrade head` re-applies them."""
    with throwaway_database_with_auth() as url:
        run_alembic(url, "upgrade", "head")
        run_alembic(url, "downgrade", "base")

        with psycopg.connect(url, autocommit=True) as conn:
            fn = conn.execute("SELECT to_regprocedure('public.handle_new_user()')").fetchone()
            assert fn is not None and fn[0] is None, "downgrade should drop handle_new_user()"
            trg = conn.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgname = 'on_auth_user_created'"
            ).fetchone()
            assert trg is not None and trg[0] == 0, "downgrade should drop the trigger"

        # Re-applying the whole stack succeeds (idempotent, reversible).
        run_alembic(url, "upgrade", "head")
        with psycopg.connect(url, autocommit=True) as conn:
            fn = conn.execute("SELECT to_regprocedure('public.handle_new_user()')").fetchone()
            assert fn is not None and fn[0] is not None


# ── The live Supabase signup/login flow ──────────────────────────────────────────────────────


def test_signup_creates_single_free_profile() -> None:
    """A fresh (pre-confirmed) signup yields exactly one ``plan='free'`` profile via the trigger."""
    with httpx.Client(timeout=30.0) as client:
        user = create_confirmed_user(client)
        try:
            with psycopg.connect(database_url()) as conn:
                rows = _profiles_for(conn, user.id)
            assert len(rows) == 1, "the handle_new_user trigger should create exactly one profile"
            assert rows[0][1] == "free"
        finally:
            delete_user(client, user.id)  # cascades the profile away — keeps the stack clean


def test_repeated_login_does_not_duplicate_profile() -> None:
    """First login creates the row (at signup); a second login must not create a duplicate."""
    with httpx.Client(timeout=30.0) as client:
        user = create_confirmed_user(client)
        try:
            # First login.
            token1 = login(client, user.email, user.password)
            assert token1
            assert _count_profiles_for(user.id) == 1

            # Second login — re-authenticating issues a new token but inserts no auth.users row,
            # so the trigger does not fire again and there is still exactly one profile.
            token2 = login(client, user.email, user.password)
            assert token2
            assert _count_profiles_for(user.id) == 1
        finally:
            delete_user(client, user.id)
