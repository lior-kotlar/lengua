"""Live Supabase Auth (GoTrue) helpers for the Phase 2.5 integration tests.

Thin wrappers over the local Supabase Auth REST API, used by ``test_profiles_bootstrap.py`` and
``test_demo_seed.py`` to exercise the *real* auth flow (so we prove the ``handle_new_user`` trigger
and the demo account against genuine signups/logins, not just minted tokens):

* :func:`create_confirmed_user` — admin-create a pre-confirmed user (``service_role``); a confirmed
  user can sign in immediately, and the trigger makes its ``profiles`` row.
* :func:`delete_user` — admin-delete a user (``service_role``); used in ``finally`` so test users
  never leak into ``auth.users`` (which the conftest does not truncate).
* :func:`get_user` — admin-fetch a user by id (to assert ``email_confirmed_at``).
* :func:`login` — password-grant login (anon key) → a real Supabase-signed access token (JWT).

Endpoint + keys come from the environment the conftest auto-sources from ``supabase status -o
env`` (``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` / ``SUPABASE_ANON_KEY`` /
``SUPABASE_JWT_SECRET``), with the well-known local CLI defaults as a fallback. None of these are
secrets — they are the fixed values the local Supabase CLI prints for everyone.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import httpx

from scripts.seed_e2e import _auth_headers, _supabase_url

# Well-known local Supabase CLI anon key (NOT a secret — the CLI signs it with the default local
# secret and prints it from ``supabase status``). Overridable via env for CI / a custom stack.
LOCAL_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)


def anon_key() -> str:
    """The anon (publishable) key used for password-grant login."""
    return os.getenv("SUPABASE_ANON_KEY") or LOCAL_ANON_KEY


def jwks_url() -> str:
    """The GoTrue JWKS endpoint. Modern Supabase signs access tokens with asymmetric keys
    (ES256), so the backend verifies real logins via JWKS rather than the HS256 shared secret."""
    return f"{_supabase_url()}/auth/v1/.well-known/jwks.json"


@dataclass(frozen=True)
class CreatedUser:
    """An admin-created, pre-confirmed auth user (with the password it can log in with)."""

    id: str
    email: str
    password: str


def create_confirmed_user(
    client: httpx.Client,
    *,
    email: str | None = None,
    password: str = "Test-pass-123",  # noqa: S107 — fixed local test credential, not a secret
) -> CreatedUser:
    """Admin-create a pre-confirmed user (unique email by default) and return its id/credentials."""
    email = email or f"bootstrap-{uuid.uuid4().hex[:12]}@lengua.test"
    resp = client.post(
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=_auth_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    resp.raise_for_status()
    return CreatedUser(id=str(resp.json()["id"]), email=email, password=password)


def delete_user(client: httpx.Client, user_id: str | uuid.UUID) -> None:
    """Admin-delete a user (best-effort cleanup; ignores a already-gone 404)."""
    resp = client.delete(
        f"{_supabase_url()}/auth/v1/admin/users/{user_id}",
        headers=_auth_headers(),
    )
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


def get_user(client: httpx.Client, user_id: str | uuid.UUID) -> dict[str, object]:
    """Admin-fetch a user by id (e.g. to read ``email_confirmed_at``)."""
    resp = client.get(
        f"{_supabase_url()}/auth/v1/admin/users/{user_id}",
        headers=_auth_headers(),
    )
    resp.raise_for_status()
    return dict(resp.json())


def login(client: httpx.Client, email: str, password: str) -> str:
    """Password-grant login → the ``access_token`` (a real Supabase-signed JWT)."""
    resp = client.post(
        f"{_supabase_url()}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key(), "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])
