"""Signup-required — no guest/anonymous mode (task 2.5.2).

Two guarantees, end to end:

* **No anonymous token issuance.** The CLI-read Supabase config (the repo-root
  ``supabase/config.toml`` the local stack and hosted projects share) has
  ``enable_anonymous_sign_ins = false`` — GoTrue will not mint guest tokens — while ordinary
  signup stays enabled (signup-required, not signup-disabled).
* **No anonymous domain writes.** Every write route requires ``current_user`` (gated in 2.4.2): an
  unauthenticated write is rejected with ``401`` before the handler runs, and no code path inserts
  domain rows for a null/anon user (asserted against the DB).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import BaseRoute

from app.db.models import Card, Language
from app.deps import get_db, get_llm_provider
from app.main import create_app

# The canonical config the Supabase CLI actually reads is the repo-ROOT supabase/config.toml
# (apps/api/tests/<this file> → parents[3] is the repo root).
_CONFIG_TOML = Path(__file__).resolve().parents[3] / "supabase" / "config.toml"
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _auth_config() -> dict[str, Any]:
    """The ``[auth]`` table from the canonical Supabase ``config.toml``."""
    data = tomllib.loads(_CONFIG_TOML.read_text(encoding="utf-8"))
    auth = data["auth"]
    assert isinstance(auth, dict)
    return auth


# ── No anonymous token issuance (config) ─────────────────────────────────────────────────────


def test_canonical_supabase_config_exists() -> None:
    """The config the CLI reads lives at the repo root (not infra/supabase)."""
    assert _CONFIG_TOML.is_file(), f"expected canonical Supabase config at {_CONFIG_TOML}"


def test_anonymous_sign_ins_disabled() -> None:
    """No guest mode: GoTrue is configured to never issue anonymous sign-in tokens."""
    assert _auth_config()["enable_anonymous_sign_ins"] is False


def test_signup_required_not_signup_disabled() -> None:
    """Accounts can be created (signup-required), there just is no anonymous path."""
    auth = _auth_config()
    assert auth["enable_signup"] is True
    assert auth["email"]["enable_signup"] is True


# ── No anonymous domain writes (routes) ──────────────────────────────────────────────────────


def _iter_api_routes(routes: list[BaseRoute]) -> Iterator[APIRoute]:
    """Yield every :class:`APIRoute`, descending into included sub-routers (FastAPI nesting)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original.routes)


def _write_routes() -> list[tuple[str, str]]:
    """Every (write-method, concrete-path) pair across the app's domain routers."""
    app = create_app(include_test_routes=False)
    pairs: set[tuple[str, str]] = set()
    for route in _iter_api_routes(app.routes):
        if route.path == "/health":
            continue
        for method in (route.methods or set()) & _WRITE_METHODS:
            pairs.add((method, re.sub(r"\{[^}]+\}", "1", route.path)))
    return sorted(pairs)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI client whose ``get_db`` / ``get_llm_provider`` are stubbed (never reached on a 401)."""
    app = create_app(include_test_routes=False)

    async def _no_db() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_db] = _no_db
    app.dependency_overrides[get_llm_provider] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


def test_write_routes_exist() -> None:
    """Guard the guard: there really are write routes to protect."""
    routes = _write_routes()
    assert len(routes) >= 4, routes
    assert ("POST", "/languages") in routes


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), _write_routes())
async def test_write_route_rejects_anonymous(client: AsyncClient, method: str, path: str) -> None:
    """No guest writes: every write endpoint returns 401 without a JWT (handler never runs)."""
    response = await client.request(method, path)
    assert response.status_code == 401, f"{method} {path} allowed an anonymous write"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anonymous_write_persists_no_domain_rows(
    multiuser_client: AsyncClient, db_session: AsyncSession
) -> None:
    """An unauthenticated write inserts nothing — there is no null/anon user code path."""
    languages_before = await db_session.scalar(select(func.count()).select_from(Language))

    # Both rejected at dependency resolution (no token) — before any DB/handler work.
    created = await multiuser_client.post("/languages", json={"name": "guest", "code": "es"})
    assert created.status_code == 401
    saved = await multiuser_client.post("/cards/save", json={"language_id": 1, "cards": []})
    assert saved.status_code == 401

    languages_after = await db_session.scalar(select(func.count()).select_from(Language))
    assert languages_after == languages_before  # no language row inserted for an anon user
    assert await db_session.scalar(select(func.count()).select_from(Card)) == 0
