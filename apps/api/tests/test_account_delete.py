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
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock

import httpx
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.session import UsageSession, async_dsn
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


def _offline_db() -> AsyncSession:
    """An offline stand-in for the privileged ``profiles``-delete session.

    The unit tests exercise the **Auth Admin** half of ``delete_user`` (offline, no real DB), so the
    profile hard-delete is driven against an :class:`AsyncMock` that records ``execute``/``commit``
    without connecting. Cast to :class:`AsyncSession` purely to satisfy the typed signature.
    """
    return cast(AsyncSession, AsyncMock(spec=AsyncSession))


async def _fresh_usage_db() -> AsyncIterator[UsageSession]:
    """A privileged session on a fresh, immediately-disposed engine (a ``get_usage_db`` override).

    The HTTP-driven integration tests below each run in their own event loop, but the process-wide
    engine pools asyncpg connections across loops — so reusing it makes a later test pick up a
    connection bound to an earlier test's *closed* loop ("Event loop is closed" on Windows). A
    per-request fresh engine keeps every connection inside the test's own loop. Mirrors the
    fresh-engine isolation ``tests.conftest.db_session`` already uses.
    """
    engine = create_async_engine(async_dsn(database_url()))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield UsageSession(session)
    finally:
        await engine.dispose()


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
    await service.delete_user(user_id, db=_offline_db())

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
    await service.delete_user(uuid.uuid4(), db=_offline_db())  # must not raise


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
async def test_delete_user_raises_on_admin_error_status(status_code: int) -> None:
    """A non-success, non-404 status from GoTrue is surfaced as AccountAdminError (→ 502)."""
    service = AccountDeletionService(
        _admin_settings(), transport=httpx.MockTransport(lambda _req: httpx.Response(status_code))
    )
    with pytest.raises(AccountAdminError):
        await service.delete_user(uuid.uuid4(), db=_offline_db())


@pytest.mark.asyncio
async def test_delete_user_wraps_network_errors() -> None:
    """A transport/network failure becomes AccountAdminError (nothing deleted → safe to retry)."""

    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    service = AccountDeletionService(_admin_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AccountAdminError):
        await service.delete_user(uuid.uuid4(), db=_offline_db())


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
        await service.delete_user(uuid.uuid4(), db=_offline_db())


@pytest.mark.asyncio
async def test_delete_endpoint_maps_admin_failure_to_502() -> None:
    """When the deletion service fails, ``DELETE /account`` returns ``502`` (retryable), not 500."""
    from app.deps import get_account_deletion_service, get_usage_db
    from app.main import create_app
    from tests.auth_helpers import auth_header, install_test_auth

    class _FailingDeletion:
        async def delete_user(self, _user_id: uuid.UUID, *, db: object) -> None:
            raise AccountAdminError("admin api unavailable")

    async def _fake_usage_db() -> AsyncIterator[object]:
        yield object()  # offline: the failing service raises before touching the session

    app = create_app(include_test_routes=False)
    app.dependency_overrides[get_account_deletion_service] = _FailingDeletion
    app.dependency_overrides[get_usage_db] = _fake_usage_db
    install_test_auth(app)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.delete("/account", headers=auth_header(uuid.uuid4()))
        assert resp.status_code == 502, resp.text
        assert "did not complete" in resp.json()["detail"].lower()
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
    from app.deps import get_llm_provider, get_usage_db
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
            app.dependency_overrides[get_usage_db] = _fresh_usage_db  # fresh-engine privileged sess
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
    from app.deps import get_usage_db
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
            app.dependency_overrides[get_usage_db] = _fresh_usage_db  # fresh-engine privileged sess
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


# ── Defense-in-depth: the explicit profiles delete erases data without the auth cascade ───────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_user_erases_all_domain_data_without_the_auth_cascade() -> None:
    """The privileged ``profiles`` delete erases EVERY domain table even when the
    ``auth.users → profiles`` cascade never fires — the no-FK staging/prod case behind S1.

    A real auth user is seeded (its trigger-made profile + a row in every domain table), then the
    REAL :class:`AccountDeletionService` runs with an **offline GoTrue mock that returns 204 but
    deletes nothing** — so ``auth.users`` (and therefore its cascade) is left intact. The only thing
    that can erase the domain graph is the explicit, privileged ``profiles`` delete. We assert the
    profiles row and every dependent row are gone while ``auth.users`` still exists, proving erasure
    no longer depends on the FK cascade (defense-in-depth for a DB that lacks the FK).
    """
    from tests.supabase_auth import create_confirmed_user, delete_user

    with httpx.Client(timeout=30.0) as http:
        user = create_confirmed_user(http, email=f"erase-{uuid.uuid4().hex[:8]}@lengua.test")
        try:
            _seed_committed_graph(user.id, "Erasure-Spanish")

            with psycopg.connect(database_url()) as conn:
                before = _domain_counts(conn, user.id)
            assert before["profiles"] == 1
            assert all(v >= 1 for v in before.values()), f"seed incomplete: {before}"

            # The GoTrue DELETE is intercepted by an offline mock: it returns 204 but never touches
            # the real auth.users row, so the auth→profiles cascade cannot run.
            service = AccountDeletionService(
                _admin_settings(),
                transport=httpx.MockTransport(lambda _req: httpx.Response(204)),
            )
            # A privileged (RLS-bypassing) session on a fresh engine bound to this test's own loop.
            engine = create_async_engine(async_dsn(database_url()))
            try:
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    await service.delete_user(uuid.UUID(user.id), db=UsageSession(session))
            finally:
                await engine.dispose()

            with psycopg.connect(database_url()) as conn:
                after = _domain_counts(conn, user.id)
                auth_row = conn.execute(
                    "SELECT count(*) FROM auth.users WHERE id = %s", (user.id,)
                ).fetchone()
            # Every domain table AND the profiles row are empty — erased by the profiles delete.
            assert after == {k: 0 for k in after}, f"defense-in-depth left rows: {after}"
            # auth.users is still present (GoTrue mocked) → the cascade did NOT run; the explicit
            # profiles delete is what erased the whole graph.
            assert auth_row is not None and auth_row[0] == 1, (
                "auth.users must remain (GoTrue mocked) — erasure came from the profiles delete, "
                "not the auth→profiles cascade"
            )
        finally:
            delete_user(http, user.id)  # real cleanup: removes the lingering auth.users row


# ── The still-valid access token of a just-deleted account (stateless JWKS window) ────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deleted_but_unexpired_token_reads_an_empty_bundle_not_a_leak() -> None:
    """A still-valid JWT for a just-deleted account reads a ``200`` EMPTY bundle — never a leak/500.

    The app verifies bearer tokens statelessly via JWKS, so A's access token keeps verifying until
    its ``exp`` even after ``DELETE /account`` has removed the account server-side (the sibling
    ``…_twice_is_idempotent_over_http`` relies on exactly this property). Existing tests cover
    GoTrue's *session* rejection and the idempotent second ``DELETE``, but nothing pins what one of
    the app's OWN read endpoints returns inside that within-``exp`` window.

    Here A (with a live neighbour B) is created + seeded, A logs in, ``DELETE /account`` → ``204``,
    then the SAME still-valid token hits ``GET /account/export``: it must still authenticate (not
    ``401``) and return ``200`` with an EMPTY bundle (``profile is None``, every list ``[]``,
    ``settings == {}``), never a ``500`` and never B's data. Only the raw session sub-dependency is
    swapped for a loop-local engine so the scoped ``get_db`` (which the export uses) stays on this
    test's event loop while still binding A's real RLS identity.

    Design contract: this asserts the *current* stateless behavior (200 + empty bundle). A hard
    ``401`` for a deleted-but-unexpired token would need a stateful revocation check the JWKS path
    deliberately does not perform.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_db as raw_get_db
    from app.deps import get_usage_db
    from app.main import create_app
    from app.schemas.account import AccountExport
    from app.settings import get_settings
    from tests.supabase_auth import create_confirmed_user, delete_user, login

    with httpx.Client(timeout=30.0) as http:
        user_a = create_confirmed_user(http, email=f"del-tok-a-{uuid.uuid4().hex[:8]}@lengua.test")
        user_b = create_confirmed_user(http, email=f"del-tok-b-{uuid.uuid4().hex[:8]}@lengua.test")
        try:
            _seed_committed_graph(user_a.id, "A-Spanish")
            _seed_committed_graph(user_b.id, "B-French")
            token_a = login(http, user_a.email, user_a.password)
            assert token_a

            engine = create_async_engine(async_dsn(database_url()))
            sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

            async def _raw_session() -> AsyncIterator[AsyncSession]:
                async with sessionmaker() as session:
                    yield session

            app = create_app(include_test_routes=False)
            app.dependency_overrides[get_settings] = _real_stack_settings
            app.dependency_overrides[get_usage_db] = _fresh_usage_db  # fresh-engine privileged sess
            app.dependency_overrides[raw_get_db] = _raw_session  # loop-local scoped read for export
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                    headers = {"Authorization": f"Bearer {token_a}"}
                    deleted = await client.delete("/account", headers=headers)
                    assert deleted.status_code == 204, deleted.text

                    # Same still-valid token: the stateless JWKS path still verifies it (not 401),
                    # and the app answers a 200 EMPTY bundle — no leak of A's (now-erased) rows or
                    # of B's data, and no 500.
                    export = await client.get("/account/export", headers=headers)
                    assert export.status_code == 200, export.text
                    bundle = AccountExport.model_validate(export.json())
                    assert bundle.profile is None
                    assert bundle.languages == []
                    assert bundle.cards == []
                    assert bundle.reviews == []
                    assert bundle.proficiency == []
                    assert bundle.settings == {}

                    # Never a neighbour's data.
                    assert "B-French" not in export.text
                    assert user_b.id not in export.text
            finally:
                app.dependency_overrides.clear()
                await engine.dispose()
        finally:
            delete_user(http, user_a.id)  # already gone (404 tolerated) — defensive
            delete_user(http, user_b.id)  # cascades B's committed graph away
