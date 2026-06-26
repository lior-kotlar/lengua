"""FastAPI request-scoped dependencies.

- :func:`get_db` — the async SQLAlchemy session (re-exported from :mod:`app.db.session` so routers
  have a single dependency-import surface).
- :func:`get_current_user` — verifies the ``Authorization: Bearer`` Supabase JWT and returns the
  typed :class:`~app.auth.CurrentUser` (id + ``email_verified``); raises ``401`` on a missing or
  invalid token (task 2.3.2). This is the canonical auth dependency.
- :func:`current_user` — a thin convenience over :func:`get_current_user` returning just the user
  **UUID**, so the Phase 1 routers/services/repositories that take a ``user_id`` keep working
  unchanged. Tests override either dependency (see ``tests/auth_helpers.py``) to authenticate as a
  given user.
- :func:`get_llm_provider` — the active LLM provider behind the ``lengua_core.llm`` seam, selected
  by ``LLM_PROVIDER`` (Groq by default). Overridden with the deterministic ``FakeLLM`` in tests.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthError, CurrentUser, decode_supabase_jwt
from app.db.session import get_db
from app.settings import Settings, get_settings
from lengua_core.llm import LLMProvider, get_provider

__all__ = [
    "DEV_USER_ID",
    "CurrentUser",
    "current_user",
    "get_current_user",
    "get_db",
    "get_llm_provider",
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


def get_llm_provider() -> LLMProvider:
    """Return the active LLM provider; tests override this with ``FakeLLM``."""
    return get_provider()
