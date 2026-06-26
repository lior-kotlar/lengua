"""FastAPI request-scoped dependencies.

- :func:`get_db` — the async SQLAlchemy session for the request, **bound to the authenticated
  user's identity** so Postgres Row-Level Security is enforced (task 2.6.2). It layers the raw
  session from :mod:`app.db.session` with :func:`app.db.rls.bind_request_identity`, so every
  router that depends on it transparently runs its queries as the ``authenticated`` role with
  ``request.jwt.claims`` set to ``current_user`` — defense-in-depth beneath the app-layer
  ``WHERE user_id = …`` scoping. Because it depends on :func:`current_user`, a session can never
  be obtained without a verified identity.
- :func:`get_current_user` — verifies the ``Authorization: Bearer`` Supabase JWT and returns the
  typed :class:`~app.auth.CurrentUser` (id + ``email_verified``); raises ``401`` on a missing or
  invalid token (task 2.3.2). This is the canonical auth dependency.
- :func:`current_user` — a thin convenience over :func:`get_current_user` returning just the user
  **UUID**, so the Phase 1 routers/services/repositories that take a ``user_id`` keep working
  unchanged. Tests override either dependency (see ``tests/auth_helpers.py``) to authenticate as a
  given user.
- :func:`get_usage_db` — a **privileged, RLS-bypassing** session for the server-only cost-guard
  counters (``llm_budget`` + the ``SECURITY DEFINER`` increment/read functions). Unlike
  :func:`get_db` it deliberately does **not** call :func:`app.db.rls.bind_request_identity`, so it
  runs as the connecting ``postgres``/owner role — the only role with EXECUTE on those functions.
  It must NEVER be used for per-user application data (see the §7 footgun note in
  ``planning/outstanding-work.md``); the per-user ``llm_usage`` reads stay on the normal
  :func:`get_db` session, where the RLS owner policy scopes them to the caller.
- :func:`get_llm_provider` — the active LLM provider behind the ``lengua_core.llm`` seam, selected
  by ``LLM_PROVIDER`` (Groq by default). Overridden with the deterministic ``FakeLLM`` in tests.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthError, CurrentUser, decode_supabase_jwt
from app.db.rls import bind_request_identity
from app.db.session import get_db as _get_session
from app.services.account import AccountDeletionService
from app.settings import Settings, get_settings
from lengua_core.llm import LLMProvider, get_provider

__all__ = [
    "DEV_USER_ID",
    "CurrentUser",
    "current_user",
    "get_account_deletion_service",
    "get_current_user",
    "get_db",
    "get_llm_provider",
    "get_usage_db",
]

# The fixed-UUID seeded dev/demo user. No longer returned by ``current_user`` in the request path
# (that is JWT-derived now), but kept as the canonical id the dev seed (``scripts.seed_dev_user``)
# and the test factories (``tests.factories.DEMO_USER_ID``) share so FK-bound inserts line up.
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# auto_error=False so a missing/!bearer header yields our own 401 (FastAPI's default is 403).
_bearer_scheme = HTTPBearer(auto_error=False, description="Supabase access token (JWT)")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """Verify the bearer token and return the authenticated :class:`~app.auth.CurrentUser`.

    Returns ``401`` (never 403) when the ``Authorization: Bearer`` header is missing/malformed or
    the token fails verification (bad signature, expired, wrong audience, ``alg: none``, …).
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")
    try:
        return decode_supabase_jwt(credentials.credentials, settings=settings)
    except AuthError as exc:
        raise _unauthorized("Invalid authentication token") from exc


async def current_user(user: Annotated[CurrentUser, Depends(get_current_user)]) -> uuid.UUID:
    """The authenticated user's id (UUID from the JWT ``sub``)."""
    return user.id


async def get_db(
    session: Annotated[AsyncSession, Depends(_get_session)],
    user_id: Annotated[uuid.UUID, Depends(current_user)],
) -> AsyncSession:
    """The request's DB session, bound to ``current_user`` so RLS is enforced (task 2.6.2).

    Wraps the raw session from :func:`app.db.session.get_db` (whose generator owns the session's
    open/close lifecycle) and stamps the authenticated identity onto it via
    :func:`app.db.rls.bind_request_identity`. Every router depends on this single choke point, so
    all application queries run as the ``authenticated`` role with the caller's ``request.jwt``
    claims — the database half of tenant isolation, beneath the app-layer ``user_id`` scoping.

    Tests that want a privileged (RLS-bypassing) session override this dependency directly (see
    ``tests/api/conftest.py``); migrations and seed scripts never use it.
    """
    bind_request_identity(session, user_id)
    return session


async def get_usage_db(
    session: Annotated[AsyncSession, Depends(_get_session)],
) -> AsyncSession:
    """A **privileged, RLS-bypassing** DB session for the server-only cost-guard counters (3.1).

    ⚠️ BOUNDARY: this deliberately skips :func:`app.db.rls.bind_request_identity`, so the session
    stays on the connecting ``postgres``/owner role rather than dropping to ``authenticated``. That
    is required — and only safe — for the global ``llm_budget`` kill-switch: its rows are
    ``REVOKE``\\d from ``authenticated``/``anon`` and written only via ``SECURITY DEFINER``
    functions the request role cannot EXECUTE, so the increment/read runs as the privileged role.

    It must **never** be used for per-user application data — running un-bound bypasses Row-Level
    Security entirely (the latent footgun flagged in §7 of ``planning/outstanding-work.md``). The
    per-user ``llm_usage`` reads use the normal :func:`get_db` session, where the RLS owner policy
    scopes them to the caller. Group 3.2/3.4 wire this into the quota gate; 3.1 only provides it.
    """
    return session


def get_llm_provider() -> LLMProvider:
    """Return the active LLM provider; tests override this with ``FakeLLM``."""
    return get_provider()


def get_account_deletion_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountDeletionService:
    """The service that hard-deletes a user via the Supabase Auth Admin API (task 2.8.3).

    Built from the server-only ``settings`` (Supabase URL + service-role key). Tests override this
    dependency to inject a fake/offline deletion service so ``DELETE /account`` can be exercised
    without a live Supabase Auth stack.
    """
    return AccountDeletionService(settings)
