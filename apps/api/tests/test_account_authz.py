"""The account endpoints act strictly on ``current_user`` — no target-user knob (task 2.8.4).

The cross-tenant guard for export/delete is *structural*: neither endpoint accepts a user-id
parameter (path, query, or body), so the only identity they can ever act on is the one derived
from the verified JWT. This is proven two ways, both offline (no DB/network needed — the delete
path calls an injected recorder instead of the real Auth Admin API):

* **Contract** — introspecting the routes (and the generated OpenAPI) shows ``GET /account/export``
  and ``DELETE /account`` declare *no* path/query/body parameters, and the public schema exposes no
  user-id parameter on either operation.
* **Behavior** — a ``DELETE /account`` request deletes *exactly* the token's user: B's request
  deletes B (never A), A's request deletes A. There is no input by which B could target A.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.deps import get_account_deletion_service, get_usage_db
from app.main import create_app
from app.routers.account import router as account_router
from tests.auth_helpers import auth_header, install_test_auth

USER_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


def _route(path: str, method: str) -> APIRoute:
    for route in account_router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and route.methods is not None
            and method in route.methods
        ):
            return route
    raise AssertionError(f"{method} {path} not found on the account router")


# ── Contract: no user-id parameter anywhere ──────────────────────────────────────────────────


def test_account_routes_take_no_client_parameters() -> None:
    """Neither route declares a path/query/body parameter — so no target user can be supplied."""
    for path, method in (("/account/export", "GET"), ("/account", "DELETE")):
        route = _route(path, method)
        assert "{" not in route.path, f"{method} {path} must not be parameterised"
        assert route.dependant.path_params == [], f"{method} {path} has path params"
        assert route.dependant.query_params == [], f"{method} {path} has query params"
        assert route.body_field is None, f"{method} {path} accepts a request body"


def test_openapi_exposes_no_user_id_parameter() -> None:
    """The public OpenAPI contract for both operations exposes no user-id parameter."""
    schema = create_app(include_test_routes=False).openapi()

    for path, method in (("/account/export", "get"), ("/account", "delete")):
        operation = schema["paths"][path][method]
        params = operation.get("parameters", [])
        names = {p["name"].lower() for p in params}
        assert not any("user" in n or "uid" in n or "id" in n for n in names), (
            f"{method.upper()} {path} exposes an identity parameter: {names}"
        )
        assert "requestBody" not in operation, f"{method.upper()} {path} declares a request body"


# ── Behavior: delete acts only on the token's user ───────────────────────────────────────────


class _RecordingDeletion:
    """Stand-in for the deletion service that records which user id it was asked to delete.

    ``delete_user`` takes the privileged ``db`` session the real service uses (and ignores it —
    these tests assert *which user* is targeted, not the DB erasure), matching the real signature.
    """

    def __init__(self) -> None:
        self.deleted: list[uuid.UUID] = []

    async def delete_user(self, user_id: uuid.UUID, *, db: object) -> None:
        self.deleted.append(user_id)


@pytest_asyncio.fixture
async def authz_client() -> AsyncIterator[tuple[AsyncClient, _RecordingDeletion]]:
    """An app whose deletion service is an offline recorder; auth verifies minted test tokens."""
    app = create_app(include_test_routes=False)
    recorder = _RecordingDeletion()

    async def _fake_usage_db() -> AsyncIterator[object]:
        # The recorder ignores it; override so the route resolves with no real DB (these are
        # offline tests — the privileged session is never opened).
        yield object()

    app.dependency_overrides[get_account_deletion_service] = lambda: recorder
    app.dependency_overrides[get_usage_db] = _fake_usage_db
    install_test_auth(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, recorder
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_acts_only_on_the_token_user(
    authz_client: tuple[AsyncClient, _RecordingDeletion],
) -> None:
    client, recorder = authz_client

    # B's request deletes B — A is never referenced (there is no parameter to reference A by).
    resp_b = await client.delete("/account", headers=auth_header(USER_B))
    assert resp_b.status_code == 204
    assert recorder.deleted == [USER_B]

    # A's request deletes A: the id is the token's `sub`, not any client-controlled input.
    resp_a = await client.delete("/account", headers=auth_header(USER_A))
    assert resp_a.status_code == 204
    assert recorder.deleted == [USER_B, USER_A]


@pytest.mark.asyncio
async def test_delete_and_export_require_a_token(
    authz_client: tuple[AsyncClient, _RecordingDeletion],
) -> None:
    client, recorder = authz_client

    assert (await client.delete("/account")).status_code == 401
    assert (await client.get("/account/export")).status_code == 401
    assert recorder.deleted == []  # an unauthenticated request never reaches the deletion service
