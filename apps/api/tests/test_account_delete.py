"""``DELETE /account`` hard-deletes the user and cascades, with no partial state (task 2.8.3).

Two layers:

* **Unit (offline)** — :class:`~app.services.account.AccountDeletionService` is driven with an
  ``httpx.MockTransport`` (no network). These assert it calls the Supabase **Auth Admin API**
  (``DELETE /auth/v1/admin/users/{id}``) with the *service-role* credentials and the id it was
  given; treats ``200``/``204``/``404`` as success; surfaces other statuses and network failures as
  :class:`~app.services.account.AccountAdminError`; and **fails closed** (never makes a request)
  when the admin credentials are unset.

* **Integration (live stack)** — the real flow end to end: two confirmed users A and B each get a
  committed domain graph; A logs in (a real Supabase JWT); ``DELETE /account`` (verifying A's real
  token and calling the live Admin API) returns ``204``; then A's ``auth.users`` row is gone, A's
  rows in *every* domain table are gone (the ``auth.users``→``profiles``→domain cascade), B's data
  is untouched, and A's old token is rejected server-side (GoTrue ``/user`` + a fresh login both
  fail).

Ordering / transactionality: the Admin delete is the single irreversible step and runs last, so a
failure (asserted in the unit tests via a ``500``) deletes nothing — there is never a partial state.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.services.account import AccountAdminError, AccountDeletionService
from app.settings import Settings
from tests.conftest import database_url

# ── Unit: the deletion service speaks the Auth Admin API correctly (offline) ──────────────────

_ADMIN_URL = "http://auth.test"
_SERVICE_KEY = "service-role-test-key"  # noqa: S105 — fake key for the offline mock transport


def _admin_settings(*, url: str = _ADMIN_URL, key: str = _SERVICE_KEY) -> Settings:
    """Settings carrying just the Supabase URL + service-role key the deletion path reads."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_url=url,
        supabase_service_role_key=SecretStr(key),
    )


@pytest.mark.asyncio
async def test_delete_user_calls_auth_admin_api_with_service_role() -> None:
    """It DELETEs ``/auth/v1/admin/users/{id}`` with the service-role key in both auth headers."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["apikey"] = request.headers.get("apikey")
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200)

    service = AccountDeletionService(_admin_settings(), transport=httpx.MockTransport(handler))
    user_id = uuid.uuid4()
    await service.delete_user(user_id)

    assert captured["method"] == "DELETE"
    assert captured["url"] == f"{_ADMIN_URL}/auth/v1/admin/users/{user_id}"
    assert captured["apikey"] == _SERVICE_KEY
    assert captured["authorization"] == f"Bearer {_SERVICE_KEY}"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 204, 404])
async def test_delete_user_treats_success_and_missing_as_done(status_code: int) -> None:
    """``200``/``204`` (deleted) and ``404`` (already gone) are all idempotent successes."""
    service = AccountDeletionService(
        _admin_settings(), transport=httpx.MockTransport(lambda _req: httpx.Response(status_code))
    )
    await service.delete_user(uuid.uuid4())  # must not raise


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
async def test_delete_user_raises_on_admin_error_status(status_code: int) -> None:
    """A non-success, non-404 status from GoTrue is surfaced as AccountAdminError (→ 502)."""
    service = AccountDeletionService(
        _admin_settings(), transport=httpx.MockTransport(lambda _req: httpx.Response(status_code))
    )
    with pytest.raises(AccountAdminError):
        await service.delete_user(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_user_wraps_network_errors() -> None:
    """A transport/network failure becomes AccountAdminError (nothing deleted → safe to retry)."""

    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    service = AccountDeletionService(_admin_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AccountAdminError):
        await service.delete_user(uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "key"), [("", _SERVICE_KEY), (_ADMIN_URL, "")])
async def test_delete_user_fails_closed_without_admin_credentials(url: str, key: str) -> None:
    """With the URL or key unset it raises *before* making any request (fail closed)."""

    def handler(_req: httpx.Request) -> httpx.Response:  # pragma: no cover - must never run
        raise AssertionError("no request should be made without admin credentials")

    service = AccountDeletionService(
        _admin_settings(url=url, key=key), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AccountAdminError):
        await service.delete_user(uuid.uuid4())


@pytest.mark.asyncio
async def test_delete_endpoint_maps_admin_failure_to_502() -> None:
    """When the deletion service fails, ``DELETE /account`` returns ``502`` (retryable), not 500."""
    from app.deps import get_account_deletion_service
    from app.main import create_app
    from tests.auth_helpers import auth_header, install_test_auth

    class _FailingDeletion:
        async def delete_user(self, _user_id: uuid.UUID) -> None:
            raise AccountAdminError("admin api unavailable")

    app = create_app(include_test_routes=False)
    app.dependency_overrides[get_account_deletion_service] = _FailingDeletion
    install_test_auth(app)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.delete("/account", headers=auth_header(uuid.uuid4()))
        assert resp.status_code == 502, resp.text
        assert "no data was removed" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ── Integration: the real DELETE /account flow against the live Supabase stack ────────────────

_DEPENDENT_TABLES = (
    "languages",
    "cards",
    "reviews",
    "proficiency",
    "user_settings",
    "llm_usage",
)


def _seed_committed_graph(user_id: str, language_name: str) -> None:
    """Commit a full domain graph for an already-existing (profile-bootstrapped) auth user."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        lang = conn.execute(
            "INSERT INTO languages (user_id, name, code) VALUES (%s, %s, 'es') RETURNING id",
            (user_id, language_name),
        ).fetchone()
        assert lang is not None
        language_id = int(lang[0])
        card = conn.execute(
            "INSERT INTO cards (user_id, language_id, front, back, saved, due) "
            "VALUES (%s, %s, 'hola', 'hello', true, now()) RETURNING id",
            (user_id, language_id),
        ).fetchone()
        assert card is not None
        conn.execute(
            "INSERT INTO cards (user_id, language_id, front, back) "
            "VALUES (%s, %s, 'hello', 'hola')",
            (user_id, language_id),
        )
        conn.execute(
            "INSERT INTO reviews (user_id, card_id, rating) VALUES (%s, %s, 3)",
            (user_id, int(card[0])),
        )
        conn.execute(
            "INSERT INTO proficiency (user_id, language_id, score) VALUES (%s, %s, 2.0)",
            (user_id, language_id),
        )
        conn.execute(
            "INSERT INTO user_settings (user_id, key, value) VALUES (%s, 'daily_total_limit', '7')",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO llm_usage (user_id, day, kind, count) "
            "VALUES (%s, current_date, 'generate', 1)",
            (user_id,),
        )


def _domain_counts(conn: psycopg.Connection, user_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    profiles = conn.execute("SELECT count(*) FROM profiles WHERE id = %s", (user_id,)).fetchone()
    assert profiles is not None
    counts["profiles"] = int(profiles[0])
    for table in _DEPENDENT_TABLES:
        row = conn.execute(
            f"SELECT count(*) FROM {table} WHERE user_id = %s", (user_id,)
        ).fetchone()
        assert row is not None
        counts[table] = int(row[0])
    return counts


def _real_stack_settings() -> Settings:
    """Settings that BOTH verify a real Supabase JWT (JWKS) AND carry the Admin credentials."""
    from scripts.seed_e2e import _service_role_key, _supabase_url
    from tests.supabase_auth import jwks_url

    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwt_secret="",
        supabase_jwks_url=jwks_url(),
        supabase_url=_supabase_url(),
        supabase_service_role_key=SecretStr(_service_role_key()),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_cascades_and_invalidates_session() -> None:
    """End to end: DELETE /account removes A entirely, leaves B intact, and kills A's session."""
    from app.deps import get_llm_provider
    from app.main import create_app
    from app.settings import get_settings
    from lengua_core.llm.fake import FakeLLM
    from scripts.seed_e2e import _auth_headers, _supabase_url
    from tests.supabase_auth import anon_key, create_confirmed_user, delete_user, login

    with httpx.Client(timeout=30.0) as http:
        user_a = create_confirmed_user(http, email=f"del-a-{uuid.uuid4().hex[:8]}@lengua.test")
        user_b = create_confirmed_user(http, email=f"del-b-{uuid.uuid4().hex[:8]}@lengua.test")
        try:
            _seed_committed_graph(user_a.id, "A-Spanish")
            _seed_committed_graph(user_b.id, "B-French")
            token_a = login(http, user_a.email, user_a.password)
            assert token_a

            # Sanity: both users start with a full committed graph.
            with psycopg.connect(database_url()) as conn:
                before_a = _domain_counts(conn, user_a.id)
                before_b = _domain_counts(conn, user_b.id)
            assert all(v >= 1 for v in before_a.values()), before_a
            assert all(v >= 1 for v in before_b.values()), before_b

            # Drive DELETE /account as A: verify A's real token (JWKS) + real Auth Admin delete.
            app = create_app(include_test_routes=False)
            app.dependency_overrides[get_settings] = _real_stack_settings
            app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
            FakeLLM.reset_call_count()
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                    resp = await client.delete(
                        "/account", headers={"Authorization": f"Bearer {token_a}"}
                    )
                assert resp.status_code == 204, resp.text
            finally:
                app.dependency_overrides.clear()

            # A is gone everywhere: auth.users row + every domain table (the cascade), B untouched.
            with psycopg.connect(database_url()) as conn:
                auth_a = conn.execute(
                    "SELECT count(*) FROM auth.users WHERE id = %s", (user_a.id,)
                ).fetchone()
                assert auth_a is not None and auth_a[0] == 0, "auth.users row for A must be gone"

                after_a = _domain_counts(conn, user_a.id)
                assert after_a == {k: 0 for k in after_a}, f"A left orphan rows: {after_a}"

                after_b = _domain_counts(conn, user_b.id)
                assert after_b == before_b, f"B's data must be untouched: {before_b} -> {after_b}"

            # A's old session is rejected server-side: GoTrue /user with the old token fails, and a
            # fresh login as A fails (the account no longer exists).
            user_check = http.get(
                f"{_supabase_url()}/auth/v1/user",
                headers={"apikey": anon_key(), "Authorization": f"Bearer {token_a}"},
            )
            assert user_check.status_code in (401, 403), user_check.text

            relogin = http.post(
                f"{_supabase_url()}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": anon_key(), "Content-Type": "application/json"},
                json={"email": user_a.email, "password": user_a.password},
            )
            assert relogin.status_code >= 400, "a deleted user must not be able to log back in"

            # The delete path touches no LLM.
            assert FakeLLM.call_count == 0

            # The Admin API also confirms A is gone (404), proving the deletion was real.
            admin_get = http.get(
                f"{_supabase_url()}/auth/v1/admin/users/{user_a.id}", headers=_auth_headers()
            )
            assert admin_get.status_code == 404
        finally:
            delete_user(http, user_a.id)  # already gone (404 tolerated) — defensive
            delete_user(http, user_b.id)  # cascades B's committed graph away


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_twice_is_idempotent_over_http() -> None:
    """Two ``DELETE /account`` calls for the same user both return ``204`` (HTTP-layer idempotency).

    The second call hits GoTrue for an already-deleted user, which answers ``404``; the service
    treats that as success, so the endpoint stays ``204``. The access token is a stateless JWT
    still inside its ``exp``, so it re-verifies (JWKS) even though GoTrue has revoked the session —
    exactly the double-tap a client could trigger by retrying a slow/networky first request.
    """
    from app.main import create_app
    from app.settings import get_settings
    from tests.supabase_auth import create_confirmed_user, delete_user, login

    with httpx.Client(timeout=30.0) as http:
        user = create_confirmed_user(http, email=f"del-twice-{uuid.uuid4().hex[:8]}@lengua.test")
        try:
            token = login(http, user.email, user.password)
            assert token

            app = create_app(include_test_routes=False)
            app.dependency_overrides[get_settings] = _real_stack_settings
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    first = await client.delete("/account", headers=headers)
                    assert first.status_code == 204, first.text
                    second = await client.delete("/account", headers=headers)
                    assert second.status_code == 204, second.text
            finally:
                app.dependency_overrides.clear()
        finally:
            delete_user(http, user.id)  # already gone (404 tolerated) — defensive
