"""Every domain route requires a JWT; only the infra probes are public (task 2.4.2).

Iterates the live route table and asserts that, **without** an ``Authorization`` header, every
domain API route returns ``401`` (the ``current_user`` dependency rejects before the handler — and
before body/query validation — runs), while the unauthenticated infra probes ``GET /health`` and
``GET /ready`` are reachable without a token (``/health`` → ``200``).

No database or LLM is needed: a missing token is rejected during dependency resolution, so the
``get_db`` / ``get_llm_provider`` dependencies (stubbed here to be safe) are never reached. This
keeps the test in the fast offline unit suite.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from starlette.routing import BaseRoute

from app.deps import get_db, get_llm_provider
from app.main import create_app

# FastAPI/Starlette built-ins (docs + schema) are not domain routes and are intentionally public.
_NON_DOMAIN_PATHS = frozenset({"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
# Unauthenticated infra probes (liveness + readiness) — intentionally public, like the docs routes.
_PUBLIC_PATHS = frozenset({"/health", "/ready"})
# Methods Starlette adds automatically; auth is not asserted for them.
_SKIP_METHODS = frozenset({"HEAD", "OPTIONS"})


def _concrete_path(path: str) -> str:
    """Fill any ``{path_param}`` with a dummy value so the URL resolves to its route."""
    return re.sub(r"\{[^}]+\}", "1", path)


def _iter_api_routes(routes: list[BaseRoute]) -> Iterator[APIRoute]:
    """Yield every :class:`APIRoute`, descending into included sub-routers.

    Current FastAPI mounts each ``include_router`` as an ``_IncludedRouter`` whose real routes
    hang off ``original_router`` rather than being flattened into ``app.routes``; we walk both so
    this works regardless of how a given FastAPI version nests them.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original.routes)


def _domain_routes() -> list[tuple[str, str]]:
    """Every (method, concrete-path) pair for the app's domain routes, minus the infra probes."""
    app = create_app(include_test_routes=False)
    pairs: list[tuple[str, str]] = []
    for route in _iter_api_routes(app.routes):
        if route.path in _NON_DOMAIN_PATHS or route.path in _PUBLIC_PATHS:
            continue
        for method in sorted((route.methods or set()) - _SKIP_METHODS):
            pairs.append((method, _concrete_path(route.path)))
    return sorted(set(pairs))


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An ASGI client whose ``get_db`` / ``get_llm_provider`` are stubbed (never reached on 401)."""
    app = create_app(include_test_routes=False)

    async def _no_db() -> AsyncIterator[None]:
        yield None  # auth rejects first, so the handler never uses this

    app.dependency_overrides[get_db] = _no_db
    app.dependency_overrides[get_llm_provider] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


def test_route_table_is_non_empty() -> None:
    """Guard the guard: the iteration must actually find domain routes."""
    routes = _domain_routes()
    assert len(routes) >= 8, routes
    # /me + the eight domain routers are all present and protected.
    assert ("GET", "/me") in routes
    assert ("GET", "/languages") in routes


@pytest.mark.asyncio
async def test_health_is_public(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), _domain_routes())
async def test_route_requires_jwt(client: AsyncClient, method: str, path: str) -> None:
    """Without a bearer token, every non-``/health`` route is rejected with 401."""
    response = await client.request(method, path)
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.headers.get("www-authenticate") == "Bearer"
