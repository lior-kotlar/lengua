"""HTTP tests for the ``current_user`` dependency via the ``/me`` smoke route (task 2.3.2).

Drives the real app over ASGI: no ``Authorization`` header -> 401; a valid Supabase JWT -> 200 with
the token's user id. No DB is needed — ``/me`` is derived entirely from the verified token.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.auth_helpers import auth_header, install_test_auth, make_supabase_jwt

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
async def test_me_with_valid_token_returns_user(client: AsyncClient) -> None:
    response = await client.get("/me", headers=auth_header(USER_ID, email="a@b.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == USER_ID
    assert body["email"] == "a@b.com"
    assert body["email_verified"] is True


@pytest.mark.asyncio
async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_non_bearer_scheme_returns_401(client: AsyncClient) -> None:
    token = make_supabase_jwt(USER_ID)
    response = await client.get("/me", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401
