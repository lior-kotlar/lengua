"""CORS allowlist tests (task 2.3.4).

A preflight from a listed origin gets an ``Access-Control-Allow-Origin`` header echoing the origin;
an unlisted origin does not. Also covers the settings parsing (comma-separated env -> list).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.settings import Settings

# One of the built-in default allowlisted origins, and an origin that is not on the list.
LISTED_ORIGIN = "http://localhost:5173"
UNLISTED_ORIGIN = "https://evil.example.com"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_preflight_from_listed_origin_is_allowed(client: AsyncClient) -> None:
    response = await client.options(
        "/me",
        headers={
            "Origin": LISTED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == LISTED_ORIGIN


@pytest.mark.asyncio
async def test_preflight_from_unlisted_origin_is_denied(client: AsyncClient) -> None:
    response = await client.options(
        "/me",
        headers={
            "Origin": UNLISTED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_simple_request_reflects_listed_origin(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": LISTED_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == LISTED_ORIGIN


@pytest.mark.asyncio
async def test_simple_request_from_unlisted_origin_has_no_cors_header(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": UNLISTED_ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_origins_parse_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.example, https://b.example")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_allow_origins == ["https://a.example", "https://b.example"]


def test_origins_default_includes_capacitor_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "capacitor://localhost" in settings.cors_allow_origins
