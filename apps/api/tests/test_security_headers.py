"""Security-response-header + CORS expose-header tests (findings S16, S17).

S17 — a baseline set of security headers (``X-Content-Type-Options`` / ``X-Frame-Options`` /
``Referrer-Policy`` / ``Strict-Transport-Security``) is stamped on **every** API response, and the
new middleware does **not** break the CORS preflight short-circuit (``CORSMiddleware`` stays the
outermost layer, so an allowed-origin ``OPTIONS`` preflight still returns the CORS headers).

S16 — the CORS layer exposes ``Retry-After`` so the cross-origin SPA can read the backoff countdown
on 429/503 responses instead of degrading to generic copy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.security_headers import SECURITY_HEADERS

# A built-in default allowlisted CORS origin (see app.settings.Settings.cors_allow_origins).
LISTED_ORIGIN = "http://localhost:5173"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_security_headers_present_on_normal_response(client: AsyncClient) -> None:
    """Every baseline security header appears, with its exact value, on a normal 200 response."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains"


@pytest.mark.asyncio
async def test_all_configured_security_headers_are_applied(client: AsyncClient) -> None:
    """The full ``SECURITY_HEADERS`` set is applied — guards a future addition to the constant."""
    response = await client.get("/health")
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value


@pytest.mark.asyncio
async def test_security_headers_present_on_error_response(client: AsyncClient) -> None:
    """The headers apply to EVERY response, including a 404 from an unknown path."""
    response = await client.get("/no-such-route")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_preflight_from_allowed_origin_still_returns_cors_headers(
    client: AsyncClient,
) -> None:
    """S17 ordering guard: the security-headers middleware must not break the CORS preflight.

    CORS stays outermost, so an allowed-origin ``OPTIONS`` preflight is still short-circuited with a
    2xx and the ``Access-Control-Allow-Origin`` header echoing the origin.
    """
    response = await client.options(
        "/me",
        headers={
            "Origin": LISTED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == LISTED_ORIGIN


@pytest.mark.asyncio
async def test_simple_request_carries_both_cors_and_security_headers(
    client: AsyncClient,
) -> None:
    """A cross-origin simple request carries the CORS allow-origin AND the security headers."""
    response = await client.get("/health", headers={"Origin": LISTED_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == LISTED_ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_retry_after_is_exposed_to_the_cross_origin_spa(client: AsyncClient) -> None:
    """S16: CORS exposes ``Retry-After`` so the SPA can read the 429/503 backoff countdown."""
    response = await client.get("/health", headers={"Origin": LISTED_ORIGIN})
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "Retry-After" in exposed
