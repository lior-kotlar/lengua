"""``ON DELETE CASCADE`` from ``profiles`` through every dependent table (task 2.8.2).

The canonical schema (``supabase/migrations/…_initial_schema.sql``) and the live Alembic schema
(``migrations/versions/…_initial_schema.py``) both declare every user table's ``user_id`` foreign
key as ``references profiles(id) on delete cascade`` (and ``profiles.id`` as
``references auth.users(id) on delete cascade``). So no migration is needed for 2.8.2 — this test
*proves* the cascade against the running Supabase schema, which is what account deletion relies on.

Each test inserts a **full graph** for one user (an ``auth.users`` row → the trigger makes the
``profiles`` row → a language, two cards, a review, a proficiency row, a setting, and an
``llm_usage`` row), asserts every dependent table has a row (so the cascade assertion can't pass
vacuously), then removes the parent and asserts **zero** remaining rows in every dependent table
(no orphans):

* deleting the ``profiles`` row cascades the six domain tables (the path 2.8.3 ultimately triggers
  via the ``auth.users``→``profiles`` cascade); and
* deleting the ``auth.users`` row cascades *through* ``profiles`` to the same six tables — the
  exact database behavior behind ``DELETE /account`` (the Auth Admin API deletes ``auth.users``).

Everything runs inside the rolled-back ``db`` transaction fixture, so no rows are committed.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

pytestmark = pytest.mark.integration

#: Every table carrying a ``user_id`` FK to ``profiles`` (all ``ON DELETE CASCADE``). Note the
#: table is ``llm_usage`` — the task text's ``gemini_usage`` is the superseded historical name.
_DEPENDENT_TABLES = (
    "languages",
    "cards",
    "reviews",
    "proficiency",
    "user_settings",
    "llm_usage",
)


def _count(conn: psycopg.Connection, table: str, user_id: uuid.UUID) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (user_id,)).fetchone()
    assert row is not None
    return int(row[0])


def _insert_full_graph(conn: psycopg.Connection, user_id: uuid.UUID) -> None:
    """Insert an ``auth.users`` row (trigger makes the profile) + one row in every domain table."""
    conn.execute(
        "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
        (user_id, f"cascade-{user_id.hex[:8]}@lengua.test"),
    )
    lang_row = conn.execute(
        "INSERT INTO languages (user_id, name, code) VALUES (%s, 'Cascade-Lang', 'es') "
        "RETURNING id",
        (user_id,),
    ).fetchone()
    assert lang_row is not None
    language_id = int(lang_row[0])

    card_row = conn.execute(
        "INSERT INTO cards (user_id, language_id, front, back, saved, due) "
        "VALUES (%s, %s, 'hola', 'hello', true, now()) RETURNING id",
        (user_id, language_id),
    ).fetchone()
    assert card_row is not None
    card_id = int(card_row[0])
    conn.execute(
        "INSERT INTO cards (user_id, language_id, front, back) VALUES (%s, %s, 'hello', 'hola')",
        (user_id, language_id),
    )

    conn.execute(
        "INSERT INTO reviews (user_id, card_id, rating) VALUES (%s, %s, 3)", (user_id, card_id)
    )
    conn.execute(
        "INSERT INTO proficiency (user_id, language_id, score) VALUES (%s, %s, 2.0)",
        (user_id, language_id),
    )
    conn.execute(
        "INSERT INTO user_settings (user_id, key, value) VALUES (%s, 'daily_total_limit', '20')",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO llm_usage (user_id, day, kind, count) "
        "VALUES (%s, current_date, 'generate', 1)",
        (user_id,),
    )


def _assert_graph_present(conn: psycopg.Connection, user_id: uuid.UUID) -> None:
    profiles = conn.execute("SELECT count(*) FROM profiles WHERE id = %s", (user_id,)).fetchone()
    assert profiles is not None and profiles[0] == 1, "the trigger should have made the profile"
    for table in _DEPENDENT_TABLES:
        assert _count(conn, table, user_id) >= 1, f"{table} must have a row before the delete"


def _assert_everything_gone(conn: psycopg.Connection, user_id: uuid.UUID) -> None:
    profiles = conn.execute("SELECT count(*) FROM profiles WHERE id = %s", (user_id,)).fetchone()
    assert profiles is not None and profiles[0] == 0, "profiles row should be gone"
    for table in _DEPENDENT_TABLES:
        assert _count(conn, table, user_id) == 0, f"{table} has orphan rows after the cascade!"


def test_deleting_profile_cascades_every_dependent_table(db: psycopg.Connection) -> None:
    """Deleting the ``profiles`` row removes all dependent rows — no orphans anywhere."""
    user_id = uuid.uuid4()
    _insert_full_graph(db, user_id)
    _assert_graph_present(db, user_id)

    db.execute("DELETE FROM profiles WHERE id = %s", (user_id,))

    _assert_everything_gone(db, user_id)


def test_deleting_auth_user_cascades_through_profile(db: psycopg.Connection) -> None:
    """Deleting the ``auth.users`` row cascades through ``profiles`` to every dependent table.

    This is the exact DB behavior behind ``DELETE /account``: the Auth Admin API removes the
    ``auth.users`` row, and the ``on delete cascade`` chain clears the profile + all domain data.
    """
    user_id = uuid.uuid4()
    _insert_full_graph(db, user_id)
    _assert_graph_present(db, user_id)

    db.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))

    _assert_everything_gone(db, user_id)
    # And the auth.users row itself is gone.
    remaining = db.execute("SELECT count(*) FROM auth.users WHERE id = %s", (user_id,)).fetchone()
    assert remaining is not None and remaining[0] == 0
