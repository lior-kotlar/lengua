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

import datetime
import uuid
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


# ── Cost-guard kill-switch privilege model (group 3.1) ───────────────────────────────────────────
#
# Two things must hold for the global LLM cost guard to be safe:
#   1. ``llm_usage`` is per-user — its RLS owner policy must hide A's counters from B (like every
#      other user table); and
#   2. ``llm_budget`` is the GLOBAL kill-switch — it must be *server-only*: an authenticated user
#      may neither SELECT/UPDATE the table nor EXECUTE the SECURITY DEFINER increment/read functions
#      (else they could trip or hide the kill-switch for everyone via PostgREST). The backend
#      reaches it only through a privileged (postgres) session.
#
# These run against the live local Supabase stack (built from the canonical SQL migration), where
# the ``authenticated``/``anon``/``service_role`` roles and the REVOKE/GRANT actually exist.

# A far-future day so these rows never collide with other tests' real "today" counters.
_KS_DAY = datetime.date(2099, 6, 1)
_INCREMENT_SIG = "public.increment_llm_usage(uuid,text,date)"
_READER_SIG = "public.get_llm_budget_count(date)"


def test_b_cannot_read_a_llm_usage(pair: tuple[SeededUser, SeededUser]) -> None:
    """``llm_usage`` honours the owner policy: B sees only its own counters, never A's."""
    a, b = pair
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO llm_usage (user_id, day, kind, count) VALUES (%s, %s, 'generate', 3) "
            "ON CONFLICT (user_id, day, kind) DO UPDATE SET count = 3",
            (a.id, _KS_DAY),
        )
        conn.execute(
            "INSERT INTO llm_usage (user_id, day, kind, count) VALUES (%s, %s, 'generate', 7) "
            "ON CONFLICT (user_id, day, kind) DO UPDATE SET count = 7",
            (b.id, _KS_DAY),
        )
    try:
        with acting_as(b.id) as conn:
            owners = {str(r[0]) for r in conn.execute("SELECT user_id FROM llm_usage").fetchall()}
            assert owners == {str(b.id)}, f"B saw foreign usage owners: {owners}"
            assert _count(conn, "SELECT count(*) FROM llm_usage WHERE user_id = %s", a.id) == 0
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM llm_usage WHERE day = %s", (_KS_DAY,))


def test_authenticated_cannot_read_or_write_llm_budget() -> None:
    """The ``authenticated`` role is *denied* SELECT/UPDATE on ``llm_budget``; postgres can read."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO llm_budget (day, count) VALUES (%s, 5) "
            "ON CONFLICT (day) DO UPDATE SET count = 5",
            (_KS_DAY,),
        )
    try:
        # A logged-in user can neither SELECT nor UPDATE the kill-switch counter.
        with acting_as(uuid.uuid4()) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count FROM llm_budget WHERE day = %s", (_KS_DAY,))
        with acting_as(uuid.uuid4()) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE llm_budget SET count = 0 WHERE day = %s", (_KS_DAY,))

        # The privileged (postgres) session still reads it, and the tamper attempt changed nothing.
        with psycopg.connect(database_url(), autocommit=True) as conn:
            row = conn.execute("SELECT count FROM llm_budget WHERE day = %s", (_KS_DAY,)).fetchone()
            assert row is not None and row[0] == 5, "authenticated must not be able to tamper"
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM llm_budget WHERE day = %s", (_KS_DAY,))


def test_authenticated_has_no_execute_on_killswitch_functions() -> None:
    """``authenticated`` holds no EXECUTE on either kill-switch function.

    Asserted via the catalog (``has_function_privilege``) rather than by actually calling the
    function as ``authenticated``: a deliberately-forbidden ``SECURITY DEFINER`` call is both
    redundant (the catalog grant is the source of truth Supabase's PostgREST RPC consults to decide
    whether to even expose it) and, on some Postgres builds, drops the backend connection. The
    real-permission-denied path is exercised on the table itself in
    ``test_authenticated_cannot_read_or_write_llm_budget`` above.
    """
    with acting_as(uuid.uuid4()) as conn:
        for sig in (_INCREMENT_SIG, _READER_SIG):
            granted = conn.execute(
                "SELECT has_function_privilege('authenticated', %s, 'EXECUTE')", (sig,)
            ).fetchone()
            assert granted is not None and granted[0] is False, f"authenticated can EXECUTE {sig}"


def test_service_role_can_execute_killswitch_functions() -> None:
    """``service_role`` (the trusted server role) retains EXECUTE on both functions."""
    with psycopg.connect(database_url()) as conn:
        for sig in (_INCREMENT_SIG, _READER_SIG):
            granted = conn.execute(
                "SELECT has_function_privilege('service_role', %s, 'EXECUTE')", (sig,)
            ).fetchone()
            assert granted is not None and granted[0] is True, f"service_role cannot EXECUTE {sig}"
