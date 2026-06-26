"""Reusable auth helpers for the test-suite (shipped by group 2.3 for the rest of Phase 2).

The backend now verifies a Supabase JWT on protected routes. These helpers let any test:

* mint a valid, Supabase-shaped HS256 token for an arbitrary user UUID
  (:func:`make_supabase_jwt`, signed with :data:`TEST_JWT_SECRET`) and wrap it as an
  ``Authorization`` header (:func:`auth_header`); and
* make an app accept those tokens — :func:`install_test_auth` overrides ``get_settings`` so the
  app verifies against :data:`TEST_JWT_SECRET`; or skip real tokens entirely and authenticate as a
  given user via :func:`authenticate_as` (a FastAPI dependency override).

Group 2.4 (which makes every route require a token) builds on these, so keep the surface stable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import FastAPI

from app.auth import CurrentUser
from app.deps import current_user, get_current_user
from app.settings import Settings, get_settings

#: A throwaway HS256 secret used only by tests (>= 32 chars, mirroring Supabase's local default).
TEST_JWT_SECRET = "test-only-super-secret-jwt-signing-key-0123456789"
#: Supabase signs access tokens with this audience.
TEST_AUDIENCE = "authenticated"


def make_supabase_jwt(
    user_id: str | uuid.UUID,
    *,
    secret: str = TEST_JWT_SECRET,
    email: str = "user@example.com",
    email_verified: bool = True,
    audience: str = TEST_AUDIENCE,
    algorithm: str = "HS256",
    expires_in: int = 3600,
    issued_at: datetime | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a Supabase-shaped access token. Defaults yield a valid, email-verified token.

    Tweak the kwargs to craft rejection cases: a past ``issued_at`` with negative ``expires_in``
    (expired), a different ``secret`` (forged signature), or a different ``audience``.
    """
    now = issued_at or datetime.now(tz=UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "aud": audience,
        "role": "authenticated",
        "email": email,
        "email_verified": email_verified,
        "user_metadata": {"email_verified": email_verified, "email": email},
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, secret, algorithm=algorithm)


def auth_header(user_id: str | uuid.UUID, **kwargs: Any) -> dict[str, str]:
    """A ready-to-pass ``{"Authorization": "Bearer <jwt>"}`` header for ``user_id``."""
    return {"Authorization": f"Bearer {make_supabase_jwt(user_id, **kwargs)}"}


def make_test_settings() -> Settings:
    """Settings whose JWT secret is :data:`TEST_JWT_SECRET` and JWKS is disabled (HS256 path)."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwt_secret=TEST_JWT_SECRET,
        supabase_jwks_url="",
    )


def install_test_auth(app: FastAPI) -> None:
    """Point the app's auth at :data:`TEST_JWT_SECRET` so minted tokens verify against it."""
    app.dependency_overrides[get_settings] = make_test_settings


def authenticate_as(
    app: FastAPI,
    user_id: str | uuid.UUID,
    *,
    email: str = "user@example.com",
    email_verified: bool = True,
) -> CurrentUser:
    """Override the app so every request is authenticated as ``user_id`` (no real token needed).

    Overrides both :func:`app.deps.get_current_user` (the typed identity) and
    :func:`app.deps.current_user` (the bare UUID the Phase 1 routers depend on). Returns the
    :class:`~app.auth.CurrentUser` it installed.
    """
    user = CurrentUser(id=uuid.UUID(str(user_id)), email=email, email_verified=email_verified)
    _override(app, get_current_user, lambda: user)
    _override(app, current_user, lambda: user.id)
    return user


def _override(app: FastAPI, dependency: Callable[..., Any], value: Callable[[], Any]) -> None:
    app.dependency_overrides[dependency] = value
