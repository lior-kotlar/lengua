"""Helpers for the Phase 2.6 Row-Level-Security tests.

The RLS tests are deliberately **DB-level and independent of the app code** (task 2.6.3): they
seed two users straight into Postgres as the privileged role, then read/write the data back
through a connection that has assumed the ``authenticated`` role with the user's
``request.jwt.claims`` set — exactly the per-request identity the backend installs
(:func:`app.db.rls.apply_identity`) — and prove the policies isolate the two tenants.

* :func:`seed_user` inserts a full per-user graph (``auth.users`` → trigger-made ``profiles`` →
  language → cards → review → proficiency → settings) as the superuser, so the rows exist
  *committed* and visible across connections (subject to RLS). It returns the ids for assertions.
* :func:`acting_as` yields a psycopg connection scoped to a user via ``SET LOCAL ROLE`` +
  ``set_config('request.jwt.claims', …, true)`` inside a transaction that is rolled back on exit.
* :func:`delete_users` removes the seeded ``auth.users`` rows (cascading every dependent row), so
  the tests never leak fixtures into the shared local stack.

The introspection helpers (:func:`rls_status`, :func:`policies_by_table`, :func:`user_id_tables`)
back the migration (2.6.1) and coverage (2.6.4) tests.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import psycopg

from tests.conftest import database_url

#: The seven per-user tables that MUST carry RLS + an owner policy.
RLS_USER_TABLES: tuple[str, ...] = (
    "profiles",
    "languages",
    "cards",
    "reviews",
    "proficiency",
    "user_settings",
    "llm_usage",
)

#: The project-wide kill-switch table. It carries no per-user *owner* policy (it is not per-user),
#: but as of group 3.1 it is under **deny-by-default RLS** (RLS enabled, zero policies) and is
#: ``REVOKE``\\d from ``authenticated``/``anon`` — only the privileged server role / the SECURITY
#: DEFINER functions (which bypass RLS) touch it.
GLOBAL_TABLE = "llm_budget"

#: The RLS tables whose primary key is an integer ``GENERATED ALWAYS AS IDENTITY`` column. Their
#: backing sequence must be usable by the ``authenticated`` role or every INSERT would fail despite
#: a table-level INSERT grant (the grant-coverage test, 2.6.4, asserts this).
INTEGER_PK_TABLES: tuple[str, ...] = ("languages", "cards", "reviews")


def build_claims(user_id: str | uuid.UUID) -> str:
    """The ``request.jwt.claims`` JSON that makes ``auth.uid()`` resolve to ``user_id``.

    Mirrors :func:`app.db.rls.build_jwt_claims` so the tests assume the *same* identity the app
    installs per request.
    """
    return json.dumps({"sub": str(user_id), "role": "authenticated"})


@dataclass(frozen=True)
class SeededUser:
    """The ids of a fully-seeded user graph, for cross-tenant assertions."""

    id: uuid.UUID
    language_id: int
    card_ids: list[int] = field(default_factory=list)


def seed_user(conn: psycopg.Connection, *, n_cards: int = 2) -> SeededUser:
    """Insert a committed full graph for a fresh random user (as the privileged role).

    The ``auth.users`` insert fires the ``handle_new_user`` trigger which creates the ``profiles``
    row; the remaining rows are inserted directly. ``conn`` must be a superuser connection (it
    bypasses RLS for the seed). A random UUID per call keeps reruns collision-free.
    """
    uid = uuid.uuid4()
    conn.execute(
        "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
        (uid, f"rls-{uid.hex[:12]}@lengua.test"),
    )
    row = conn.execute(
        "INSERT INTO languages (user_id, name, code) VALUES (%s, %s, 'es') RETURNING id",
        (uid, f"Lang-{uid.hex[:8]}"),
    ).fetchone()
    assert row is not None
    language_id = int(row[0])

    card_ids: list[int] = []
    for i in range(n_cards):
        crow = conn.execute(
            "INSERT INTO cards (user_id, language_id, front, back, saved, due) "
            "VALUES (%s, %s, %s, %s, true, now()) RETURNING id",
            (uid, language_id, f"front-{uid.hex[:6]}-{i}", f"back-{uid.hex[:6]}-{i}"),
        ).fetchone()
        assert crow is not None
        card_ids.append(int(crow[0]))

    conn.execute(
        "INSERT INTO reviews (user_id, card_id, rating) VALUES (%s, %s, 3)",
        (uid, card_ids[0]),
    )
    conn.execute(
        "INSERT INTO proficiency (user_id, language_id, score) VALUES (%s, %s, 0.5)",
        (uid, language_id),
    )
    conn.execute(
        "INSERT INTO user_settings (user_id, key, value) VALUES (%s, 'daily_goal', '20')",
        (uid,),
    )
    return SeededUser(id=uid, language_id=language_id, card_ids=card_ids)


def delete_users(conn: psycopg.Connection, *users: SeededUser) -> None:
    """Delete the seeded ``auth.users`` rows (cascades every dependent row). Best-effort cleanup."""
    ids = [u.id for u in users]
    if ids:
        conn.execute("DELETE FROM auth.users WHERE id = ANY(%s)", (ids,))


@contextlib.contextmanager
def acting_as(user_id: str | uuid.UUID) -> Iterator[psycopg.Connection]:
    """Yield a connection scoped to ``user_id`` (``authenticated`` role + JWT claims), then undo.

    The role switch + claim are ``SET LOCAL`` / transaction-local, so opening the (non-autocommit)
    connection auto-begins a transaction, the identity applies to it, and the ``finally`` rollback
    both undoes any writes and clears the identity before the connection closes — the same
    lifecycle the request-scoped app session has.
    """
    conn = psycopg.connect(database_url())
    try:
        conn.execute(f"SET LOCAL ROLE {_AUTHENTICATED}")
        conn.execute("SELECT set_config('request.jwt.claims', %s, true)", (build_claims(user_id),))
        yield conn
    finally:
        conn.rollback()
        conn.close()


_AUTHENTICATED = "authenticated"


# ── Introspection (migration 2.6.1 + coverage 2.6.4) ───────────────────────────────────────────


def rls_status(conn: psycopg.Connection) -> dict[str, bool]:
    """Map ``public`` base-table name → ``relrowsecurity`` (whether RLS is enabled)."""
    rows = conn.execute(
        "SELECT c.relname, c.relrowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
    ).fetchall()
    return {str(r[0]): bool(r[1]) for r in rows}


def policies_by_table(conn: psycopg.Connection) -> dict[str, list[str]]:
    """Map ``public`` table name → its list of policy names (from ``pg_policies``)."""
    rows = conn.execute(
        "SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public'"
    ).fetchall()
    out: dict[str, list[str]] = {}
    for table, policy in rows:
        out.setdefault(str(table), []).append(str(policy))
    return out


def user_id_tables(conn: psycopg.Connection) -> set[str]:
    """The set of ``public`` base tables that carry a ``user_id`` column.

    These are exactly the tables that MUST have RLS + an owner policy — the coverage test fails if
    a future ``user_id``-bearing table is added without them.
    """
    rows = conn.execute(
        "SELECT c.table_name FROM information_schema.columns c "
        "JOIN information_schema.tables t "
        "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND c.column_name = 'user_id' "
        "AND t.table_type = 'BASE TABLE'"
    ).fetchall()
    return {str(r[0]) for r in rows}


# ── Role-grant introspection (coverage 2.6.4) ──────────────────────────────────────────────────
#
# RLS governs *which rows* a role may touch, but the role still needs the underlying table/sequence
# privilege to touch any row at all. Supabase grants these to ``authenticated`` by default — an
# implicit dependency the coverage test pins so a future table added without the default grants (or
# a revoked grant) reds CI instead of 500ing on the first real authenticated write.


def has_table_privilege(conn: psycopg.Connection, role: str, table: str, privilege: str) -> bool:
    """Whether ``role`` holds ``privilege`` (SELECT/INSERT/UPDATE/DELETE/…) on ``public.table``."""
    row = conn.execute(
        "SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{table}", privilege)
    ).fetchone()
    assert row is not None
    return bool(row[0])


def identity_sequence(conn: psycopg.Connection, table: str, column: str = "id") -> str | None:
    """The name of the sequence backing ``public.table.column`` (identity/serial), or ``None``."""
    row = conn.execute(
        "SELECT pg_get_serial_sequence(%s, %s)", (f"public.{table}", column)
    ).fetchone()
    return None if row is None else (None if row[0] is None else str(row[0]))


def has_sequence_privilege(
    conn: psycopg.Connection, role: str, sequence: str, privilege: str
) -> bool:
    """Whether ``role`` holds ``privilege`` (USAGE/SELECT/UPDATE) on ``sequence``."""
    row = conn.execute(
        "SELECT has_sequence_privilege(%s, %s, %s)", (role, sequence, privilege)
    ).fetchone()
    assert row is not None
    return bool(row[0])


def has_function_privilege(conn: psycopg.Connection, role: str, signature: str) -> bool:
    """Whether ``role`` holds EXECUTE on function ``signature`` (e.g. ``public.fn(uuid, date)``)."""
    row = conn.execute(
        "SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, signature)
    ).fetchone()
    assert row is not None
    return bool(row[0])
