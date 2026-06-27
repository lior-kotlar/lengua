"""CORS allowlist tests (tasks 2.3.4 + 6.10.1).

A preflight from a listed origin gets an ``Access-Control-Allow-Origin`` header echoing the origin;
an unlisted origin does not. Also covers the settings parsing (comma-separated env -> list) and the
per-environment hardening from 6.10.1: the configured allowlist is exact, wildcard-free origins only
(never ``allow_origins=["*"]``), in every environment including prod.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.settings import Settings, get_settings

# One of the built-in default allowlisted origins, and an origin that is not on the list.
LISTED_ORIGIN = "http://localhost:5173"
UNLISTED_ORIGIN = "https://evil.example.com"


def _configured_cors_kwargs(app: FastAPI) -> dict[str, object]:
    """Return the kwargs the app's :class:`CORSMiddleware` was actually installed with.

    Introspects the Starlette middleware stack rather than the settings, so the assertion is against
    what the running app enforces — not just what is configured upstream.
    """
    for middleware in app.user_middleware:
        # cast: Starlette types ``.cls`` as a middleware factory, so a direct ``is`` check trips
        # mypy's non-overlapping-identity rule; compare class identity via ``object``.
        if cast(object, middleware.cls) is CORSMiddleware:
            return dict(middleware.kwargs)
    raise AssertionError("CORSMiddleware is not installed on the app")


def _contains_wildcard(origins: list[str]) -> bool:
    """True if any allowlisted origin is, or embeds, a ``*`` wildcard."""
    return any("*" in str(origin) for origin in origins)


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


# ── 6.10.1 — no wildcard in any environment (incl. prod) ────────────────────────────────────────


def test_default_origins_contain_no_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The built-in default allowlist is explicit origins only — never ``*``."""
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "*" not in settings.cors_allow_origins
    assert not _contains_wildcard(settings.cors_allow_origins)


def test_middleware_is_not_configured_with_a_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard the insecure (and, with credentials, invalid) ``allow_origins=["*"]`` regression.

    A wildcard origin combined with ``allow_credentials=True`` is both a security hole (any site
    could make credentialed cross-origin calls) and an invalid combination per the Fetch spec
    (browsers reject ``Access-Control-Allow-Origin: *`` on a credentialed response). Assert the
    middleware the app actually installs pairs credentials with an explicit, wildcard-free
    allowlist — so a future edit to ``allow_origins=["*"]`` fails CI here.
    """
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    get_settings.cache_clear()
    options = _configured_cors_kwargs(create_app(include_test_routes=False))

    origins = options["allow_origins"]
    assert isinstance(origins, list)
    assert origins, "CORS allow_origins must be a non-empty, explicit allowlist"
    assert "*" not in origins
    assert not _contains_wildcard(origins)
    # The dangerous combination (credentials + wildcard) must never coexist.
    assert options.get("allow_credentials") is True
    assert "*" not in origins


def test_prod_shaped_origins_are_exact_and_wildcard_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prod-style allowlist (exact staging/prod web origins) parses with no wildcard.

    Mirrors the documented prod config: ``CORS_ALLOW_ORIGINS`` set to the exact deployed web
    origins (Vercel URLs / custom domains), comma-separated, with no ``*``.
    """
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "https://lengua.vercel.app, https://app.lengua.example",
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_allow_origins == [
        "https://lengua.vercel.app",
        "https://app.lengua.example",
    ]
    assert "*" not in settings.cors_allow_origins
    assert not _contains_wildcard(settings.cors_allow_origins)


@pytest.mark.asyncio
async def test_prod_shaped_unlisted_origin_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a prod-style allowlist active, an un-allowlisted origin gets no CORS header."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://lengua.vercel.app")
    get_settings.cache_clear()
    try:
        transport = ASGITransport(app=create_app(include_test_routes=False))
        async with AsyncClient(transport=transport, base_url="http://testserver") as prod_client:
            allowed = await prod_client.get(
                "/health", headers={"Origin": "https://lengua.vercel.app"}
            )
            assert allowed.headers.get("access-control-allow-origin") == "https://lengua.vercel.app"

            denied = await prod_client.get("/health", headers={"Origin": UNLISTED_ORIGIN})
            assert "access-control-allow-origin" not in denied.headers
    finally:
        # Don't leak the prod-shaped settings into the process-wide cache for later tests.
        get_settings.cache_clear()
