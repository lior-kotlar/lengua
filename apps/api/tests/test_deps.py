"""Unit tests for the ``current_user`` auth dependency (task 2.3.2), driven offline.

A missing/invalid token is rejected during dependency resolution — before the handler (and before
the DB) is reached — so these run in the fast offline suite with no Postgres:

* the HTTP cases hit the JWT-protected ``GET /me`` and assert ``401`` for no token / garbage /
  non-Bearer scheme;
* a direct call asserts a *valid* token resolves to the typed :class:`~app.auth.CurrentUser`.

The full ``GET /me`` response (profile plan + per-language proficiency, which needs the DB) is
covered by the integration ``tests/test_me.py`` (task 2.4.4).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.auth import CurrentUser
from app.deps import get_current_user
from app.main import create_app
from tests.auth_helpers import (
    install_test_auth,
    make_supabase_jwt,
    make_test_settings,
)

USER_ID = "12345678-1234-5678-1234-567812345678"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An ASGI client bound to an app whose JWT secret is the test secret (no DB touched)."""
    app = create_app()
    install_test_auth(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/me")
    assert response.status_code == 401
    # 401 (not FastAPI's default 403 for HTTPBearer) and advertises the scheme.
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_non_bearer_scheme_returns_401(client: AsyncClient) -> None:
    token = make_supabase_jwt(USER_ID)
    response = await client.get("/me", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_accepts_valid_token() -> None:
    """A valid Supabase-shaped token resolves to the typed identity (no HTTP/DB needed)."""
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=make_supabase_jwt(USER_ID, email="a@b.com")
    )
    user = await get_current_user(credentials, make_test_settings())
    assert isinstance(user, CurrentUser)
    assert user.id == uuid.UUID(USER_ID)
    assert user.email == "a@b.com"
    assert user.email_verified is True
