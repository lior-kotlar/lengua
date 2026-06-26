"""DB-level cross-tenant isolation, independent of the app code (task 2.6.3).

These tests talk to Postgres directly (raw psycopg, no app/ORM): they seed two users as the
privileged role, then act as user **B** — assuming the ``authenticated`` role with B's
``request.jwt.claims`` exactly as the backend does per request — and prove that B can neither read
nor mutate user **A**'s ``cards`` / ``languages`` / ``reviews`` / ``proficiency`` / ``settings``.
A privileged (superuser) connection then confirms A's rows are still there — proving RLS *blocked*
B, rather than the rows simply being absent. Symmetry (A cannot see B) is checked too.

This is the database half of tenant isolation; the app-layer half is ``test_cross_tenant_app.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from tests.conftest import _skip_if_db_unreachable, database_url
from tests.rls_helpers import SeededUser, acting_as, delete_users, seed_user

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pair() -> Iterator[tuple[SeededUser, SeededUser]]:
    """Seed two committed users (A, B) for the module; delete them (cascading) at teardown.

    No test mutates A's or B's rows (cross-tenant writes are blocked by RLS and ``acting_as``
    rolls back), so one seeding serves the whole module.
    """
    _skip_if_db_unreachable()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        a = seed_user(conn)
        b = seed_user(conn)
    try:
        yield a, b
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            delete_users(conn, a, b)


def _count(conn: psycopg.Connection, sql: str, *params: object) -> int:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def test_b_cannot_read_a_rows(pair: tuple[SeededUser, SeededUser]) -> None:
    """Under B's identity, every per-user table shows only B's rows — never A's."""
    a, b = pair
    with acting_as(b.id) as conn:
        # B sees its own card(s) and none of A's, even with no WHERE on user_id.
        visible = {str(r[0]) for r in conn.execute("SELECT user_id FROM cards").fetchall()}
        assert visible == {str(b.id)}, f"B saw foreign card owners: {visible}"

        # A's specific rows are invisible to B across all five user tables.
        assert _count(conn, "SELECT count(*) FROM cards WHERE id = ANY(%s)", a.card_ids) == 0
        assert _count(conn, "SELECT count(*) FROM languages WHERE id = %s", a.language_id) == 0
        assert _count(conn, "SELECT count(*) FROM reviews WHERE user_id = %s", a.id) == 0
        assert _count(conn, "SELECT count(*) FROM proficiency WHERE user_id = %s", a.id) == 0
        assert _count(conn, "SELECT count(*) FROM user_settings WHERE user_id = %s", a.id) == 0


def test_b_update_of_a_card_affects_zero_rows(pair: tuple[SeededUser, SeededUser]) -> None:
    """B's UPDATE of A's card changes nothing; a superuser confirms A's row is untouched."""
    a, b = pair
    a_card = a.card_ids[0]
    with acting_as(b.id) as conn:
        cur = conn.execute("UPDATE cards SET front = 'HACKED' WHERE id = %s", (a_card,))
        assert cur.rowcount == 0, "RLS should hide A's card from B's UPDATE"

    with psycopg.connect(database_url(), autocommit=True) as conn:
        row = conn.execute("SELECT front FROM cards WHERE id = %s", (a_card,)).fetchone()
        assert row is not None and row[0] != "HACKED", "A's card was mutated across tenants!"


def test_b_delete_of_a_rows_affects_zero_rows(pair: tuple[SeededUser, SeededUser]) -> None:
    """B's DELETE of A's card / language changes nothing; a superuser confirms they survive."""
    a, b = pair
    a_card = a.card_ids[0]
    with acting_as(b.id) as conn:
        assert conn.execute("DELETE FROM cards WHERE id = %s", (a_card,)).rowcount == 0
        assert conn.execute("DELETE FROM languages WHERE id = %s", (a.language_id,)).rowcount == 0

    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _count(conn, "SELECT count(*) FROM cards WHERE id = %s", a_card) == 1
        assert _count(conn, "SELECT count(*) FROM languages WHERE id = %s", a.language_id) == 1


def test_b_cannot_forge_a_row_owned_by_a(pair: tuple[SeededUser, SeededUser]) -> None:
    """B inserting a card stamped with A's ``user_id`` is rejected by the WITH CHECK clause."""
    a, b = pair
    with (
        acting_as(b.id) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "INSERT INTO cards (user_id, language_id, front, back) VALUES (%s, %s, 'x', 'y')",
            (a.id, a.language_id),
        )

    # The forged row never lands.
    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _count(conn, "SELECT count(*) FROM cards WHERE front = 'x' AND back = 'y'") == 0


def test_isolation_is_symmetric(pair: tuple[SeededUser, SeededUser]) -> None:
    """A likewise cannot see B's rows — isolation runs both ways."""
    a, b = pair
    with acting_as(a.id) as conn:
        visible = {str(r[0]) for r in conn.execute("SELECT user_id FROM cards").fetchall()}
        assert visible == {str(a.id)}, f"A saw foreign card owners: {visible}"
        assert _count(conn, "SELECT count(*) FROM cards WHERE id = ANY(%s)", b.card_ids) == 0
