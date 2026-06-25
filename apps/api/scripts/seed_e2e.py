"""Seed a fresh test database with a deterministic demo account for E2E (task 0.4.4).

What it creates (idempotently):

1. **The demo auth user** — via the Supabase **Auth Admin API**
   (``POST /auth/v1/admin/users`` with the ``service_role`` key, ``email_confirm=true``). The
   ``handle_new_user`` trigger on ``auth.users`` then inserts the matching ``profiles`` row, so
   we never write ``profiles`` directly.
2. **One language** for that user.
3. **A non-empty set of due cards** (recognition + production pairs, ``saved=true``,
   ``due=now``) so the review screen has something to show.

Idempotency: re-running finds the existing demo user (by email) instead of recreating it, and
the language/card inserts use ``ON CONFLICT``/existence checks — so the E2E stack can seed on
every run without erroring or duplicating.

Config (env, with local Supabase CLI defaults):

- ``SUPABASE_URL``               default ``http://127.0.0.1:54321``
- ``SUPABASE_SERVICE_ROLE_KEY``  default = the well-known local demo service-role JWT
- ``DATABASE_URL``               default ``postgresql://postgres:postgres@127.0.0.1:54322/postgres``

Run:  ``uv run python scripts/seed_e2e.py``
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx
import psycopg

# Well-known local Supabase CLI service-role JWT (NOT a secret — this is the fixed value the CLI
# signs with the default local ``JWT_SECRET`` and prints as ``SERVICE_ROLE_KEY`` from
# ``supabase status``). Overridable via ``SUPABASE_SERVICE_ROLE_KEY`` for CI / hosted projects;
# the test fixtures also auto-source it from ``supabase status -o env`` when unset.
LOCAL_SERVICE_ROLE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)
DEFAULT_SUPABASE_URL = "http://127.0.0.1:54321"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# The demo / reviewer account. Stable so Playwright (and store reviewers later) can log in with
# fixed credentials.
DEMO_EMAIL = "demo@lengua.test"
DEMO_PASSWORD = "demo-password-123"  # noqa: S105 — fixed local test credential, not a secret
DEMO_LANGUAGE = "Spanish"


@dataclass(frozen=True)
class SeedResult:
    """What the seed produced/found — returned so tests can assert on it."""

    user_id: str
    language_id: int
    card_count: int


def _supabase_url() -> str:
    return os.getenv("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")


def _service_role_key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or LOCAL_SERVICE_ROLE_KEY


def _database_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def _auth_headers() -> dict[str, str]:
    key = _service_role_key()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _find_user_id_by_email(client: httpx.Client, email: str) -> str | None:
    """Return the auth user id for ``email`` if it already exists, else ``None``."""
    resp = client.get(
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=_auth_headers(),
        params={"page": 1, "per_page": 200},
    )
    resp.raise_for_status()
    for user in resp.json().get("users", []):
        if user.get("email") == email:
            user_id = user.get("id")
            return str(user_id) if user_id is not None else None
    return None


def ensure_demo_user(client: httpx.Client) -> str:
    """Create the demo auth user (or return the existing one's id). Idempotent.

    Uses the Auth Admin API with ``email_confirm=true`` so the account can sign in immediately;
    the ``handle_new_user`` trigger creates the ``profiles`` row as a side effect.
    """
    existing = _find_user_id_by_email(client, DEMO_EMAIL)
    if existing is not None:
        return existing

    resp = client.post(
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=_auth_headers(),
        json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "email_confirm": True,
        },
    )
    # If two seeders race, the API returns a 4xx for the duplicate — fall back to a lookup.
    if resp.status_code in (409, 422):
        found = _find_user_id_by_email(client, DEMO_EMAIL)
        if found is not None:
            return found
    resp.raise_for_status()
    return str(resp.json()["id"])


def _ensure_profile(conn: psycopg.Connection, user_id: str) -> None:
    """Make sure the ``profiles`` row exists for ``user_id``.

    Normally the ``handle_new_user`` trigger creates it when the auth user is inserted. This is
    a defensive backstop for the case where the auth user already existed but its profile was
    cleared (e.g. a test truncated ``profiles`` without deleting the auth user) — keeps the seed
    idempotent against partial states.
    """
    conn.execute(
        "INSERT INTO profiles (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
        (user_id,),
    )


def _ensure_language(conn: psycopg.Connection, user_id: str) -> int:
    """Insert the demo language if absent; return its id. Relies on ``UNIQUE (user_id, name)``."""
    conn.execute(
        "INSERT INTO languages (user_id, name, code) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, name) DO NOTHING",
        (user_id, DEMO_LANGUAGE, "es"),
    )
    row = conn.execute(
        "SELECT id FROM languages WHERE user_id = %s AND name = %s",
        (user_id, DEMO_LANGUAGE),
    ).fetchone()
    assert row is not None  # just inserted or already present
    return int(row[0])


# Fixed demo sentences → each becomes a recognition + production card pair.
_DEMO_SENTENCES = (
    ("Hola, ¿cómo estás?", "Hello, how are you?", ["hola"]),
    ("Quiero aprender español.", "I want to learn Spanish.", ["aprender", "español"]),
    ("El gato duerme en la silla.", "The cat sleeps on the chair.", ["gato", "silla"]),
)


def _ensure_cards(conn: psycopg.Connection, user_id: str, language_id: int) -> int:
    """Insert the demo due cards if the deck is empty; return the total card count.

    Idempotent: if the user already has cards for this language we leave them untouched.
    """
    existing = conn.execute(
        "SELECT count(*) FROM cards WHERE user_id = %s AND language_id = %s",
        (user_id, language_id),
    ).fetchone()
    assert existing is not None
    if existing[0] == 0:
        for sentence, translation, used in _DEMO_SENTENCES:
            used_json = json.dumps(used)
            for direction, front, back in (
                ("recognition", sentence, translation),
                ("production", translation, sentence),
            ):
                conn.execute(
                    "INSERT INTO cards "
                    "(user_id, language_id, front, back, used_words, direction, saved, due) "
                    "VALUES (%s, %s, %s, %s, %s::jsonb, %s, true, now())",
                    (user_id, language_id, front, back, used_json, direction),
                )

    total = conn.execute(
        "SELECT count(*) FROM cards WHERE user_id = %s AND language_id = %s",
        (user_id, language_id),
    ).fetchone()
    assert total is not None
    return int(total[0])


def seed() -> SeedResult:
    """Run the full idempotent seed and return what was created/found."""
    with httpx.Client(timeout=30.0) as client:
        user_id = ensure_demo_user(client)

    with psycopg.connect(_database_url(), autocommit=True) as conn:
        _ensure_profile(conn, user_id)
        language_id = _ensure_language(conn, user_id)
        card_count = _ensure_cards(conn, user_id, language_id)

    return SeedResult(user_id=user_id, language_id=language_id, card_count=card_count)


def main() -> int:
    result = seed()
    print(
        f"Seeded demo account {DEMO_EMAIL} (user {result.user_id}): "
        f"language {result.language_id}, {result.card_count} cards."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
