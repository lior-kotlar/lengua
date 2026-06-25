"""Seed the fixed dev-user profile (task 1.4.4).

A single deterministic profile whose id is a fixed UUID (:data:`DEV_USER_ID`). The FastAPI app
uses it as the placeholder ``current_user`` until Phase 2 wires real Supabase-JWT auth.

One idempotent entry point, two environments:

- **Bare Alembic-managed Postgres** (``alembic upgrade head`` on a fresh DB) — ``profiles`` has
  no ``auth.users`` foreign key, so the profile is inserted directly. This is the task's verify
  target.
- **Supabase** — ``profiles.id`` references ``auth.users(id)``, so a backing auth user with the
  *same* fixed id is created first via the Auth Admin API (the same pattern as
  ``seed_e2e.py``); the ``handle_new_user`` trigger then makes the profile.

Idempotent: an existence check on the auth user + ``INSERT … ON CONFLICT DO NOTHING`` mean
re-running adds nothing, so it is safe to run on every boot / deploy.

Config (env, with local Supabase CLI defaults):

- ``DATABASE_URL``               default ``postgresql://postgres:postgres@127.0.0.1:54322/postgres``
- ``SUPABASE_URL``               default ``http://127.0.0.1:54321``     (Supabase path only)
- ``SUPABASE_SERVICE_ROLE_KEY``  default = the well-known local demo key (Supabase path only)

Run:  ``uv run python scripts/seed_dev_user.py``
"""

from __future__ import annotations

import os

import httpx
import psycopg

from scripts.seed_e2e import _auth_headers, _supabase_url

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# The fixed dev user. ``DEV_USER_ID`` MUST equal ``tests.factories.DEMO_USER_ID`` so factory-built
# rows (whose ``user_id`` defaults to that UUID) line up with the seeded profile / ``current_user``
# — ``tests/db/test_seed_dev_user.py`` asserts they stay in sync. The email/password back the
# Supabase auth user (a fixed local dev credential, not a secret).
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
DEV_EMAIL = "dev@lengua.test"
DEV_PASSWORD = "dev-password-123"  # noqa: S105 — fixed local dev credential, not a secret


def _database_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def _auth_users_present(conn: psycopg.Connection) -> bool:
    """True when an ``auth.users`` table exists (a Supabase DB, not a bare Alembic DB)."""
    row = conn.execute("SELECT to_regclass('auth.users')").fetchone()
    return row is not None and row[0] is not None


def _dev_auth_user_exists(client: httpx.Client) -> bool:
    """True if the dev auth user (by fixed id) already exists in Supabase Auth."""
    resp = client.get(
        f"{_supabase_url()}/auth/v1/admin/users/{DEV_USER_ID}",
        headers=_auth_headers(),
    )
    return resp.status_code == 200


def ensure_dev_auth_user(client: httpx.Client) -> None:
    """Create the dev auth user with the fixed id via the Auth Admin API (idempotent).

    GoTrue honors an explicit ``id`` on admin-create, so the resulting ``auth.users`` /
    trigger-made ``profiles`` row carries :data:`DEV_USER_ID` — a stable dev UUID across
    environments. ``email_confirm=true`` lets the account sign in immediately (Phase 2).
    """
    if _dev_auth_user_exists(client):
        return
    resp = client.post(
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=_auth_headers(),
        json={
            "id": DEV_USER_ID,
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD,
            "email_confirm": True,
        },
    )
    # A racing seeder may have created it between the check and now — treat as success.
    if resp.status_code in (409, 422):
        return
    resp.raise_for_status()


def seed_dev_user(database_url: str | None = None) -> str:
    """Ensure exactly one ``profiles`` row with :data:`DEV_USER_ID` exists; return that id.

    On Supabase, a backing ``auth.users`` row is created first (the FK requires it); on bare
    Postgres the profile is inserted directly.
    """
    url = database_url or _database_url()
    with psycopg.connect(url, autocommit=True) as conn:
        if _auth_users_present(conn):
            with httpx.Client(timeout=30.0) as client:
                ensure_dev_auth_user(client)
        # No-op when the trigger already made the row; the backstop covers a truncated profile
        # whose auth user still exists.
        conn.execute(
            "INSERT INTO profiles (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (DEV_USER_ID,),
        )
    return DEV_USER_ID


def main() -> int:
    user_id = seed_dev_user()
    print(f"Seeded dev user profile {user_id} ({DEV_EMAIL}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
