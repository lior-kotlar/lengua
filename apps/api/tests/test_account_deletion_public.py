"""The public, unauthenticated account-deletion flow (Phase 8, task 8.3.1).

Three layers, mirroring ``test_account_delete.py``:

* **Token unit** — :mod:`app.deletion_tokens` sign/verify round-trips, and rejects tampered,
  expired, and malformed tokens.
* **Service / mailer unit (offline)** — the email→auth-user-id admin lookup
  (``find_auth_user_id_by_email``) driven with an ``httpx.MockTransport``; the mailer seam
  (:mod:`app.mailer`) selection + send path; and the two public endpoints exercised
  over ASGI with the deletion service, mailer, rate limiter, and privileged session all overridden —
  asserting the generic (non-enumerating) acknowledgement, the per-email rate limit, and the
  token→cascade wiring.
* **Integration (live stack)** — the real ``request → email link → confirm`` path end to end: the
  request endpoint resolves the email via the live Auth Admin API and mails a signed token (captured
  by a spy mailer); confirming it removes the user's ``auth.users`` row and every domain row (the
  cascade), leaving a neighbour untouched.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.deletion_tokens import (
    DELETION_TOKEN_TTL_SECONDS,
    DeletionTokenError,
    sign_deletion_token,
    verify_deletion_token,
)
from app.mailer import LoggingMailer, Mailer, ResendMailer, build_mailer, get_mailer
from app.ratelimit import InProcessRateLimiter
from app.services.account import AccountAdminError, AccountDeletionService
from app.settings import Settings

# ── Token unit tests (offline) ────────────────────────────────────────────────────────────────

_TOKEN_SETTINGS = Settings(  # type: ignore[call-arg]
    _env_file=None, supabase_service_role_key=SecretStr("service-role-test-key")
)


def test_sign_then_verify_round_trips_the_user_id() -> None:
    user_id = uuid.uuid4()
    token = sign_deletion_token(user_id, settings=_TOKEN_SETTINGS, now=1000.0)
    assert verify_deletion_token(token, settings=_TOKEN_SETTINGS, now=1000.0) == user_id


def test_verify_rejects_a_tampered_signature() -> None:
    token = sign_deletion_token(uuid.uuid4(), settings=_TOKEN_SETTINGS, now=1000.0)
    payload_b64, _sig = token.split(".", 1)
    forged = f"{payload_b64}.{'A' * 43}"  # a plausible-length but wrong signature
    with pytest.raises(DeletionTokenError):
        verify_deletion_token(forged, settings=_TOKEN_SETTINGS, now=1000.0)


def test_verify_rejects_an_expired_token() -> None:
    token = sign_deletion_token(uuid.uuid4(), settings=_TOKEN_SETTINGS, now=1000.0)
    later = 1000.0 + DELETION_TOKEN_TTL_SECONDS + 1
    with pytest.raises(DeletionTokenError):
        verify_deletion_token(token, settings=_TOKEN_SETTINGS, now=later)


@pytest.mark.parametrize("bad", ["", "no-dot", "not.base64!!", "@@@.@@@"])
def test_verify_rejects_malformed_tokens(bad: str) -> None:
    with pytest.raises(DeletionTokenError):
        verify_deletion_token(bad, settings=_TOKEN_SETTINGS, now=1000.0)


def test_verify_rejects_a_token_signed_with_a_different_key() -> None:
    """A token minted with one service-role key does not verify under another (key isolation)."""
    other = Settings(_env_file=None, supabase_service_role_key=SecretStr("a-different-key"))  # type: ignore[call-arg]
    token = sign_deletion_token(uuid.uuid4(), settings=_TOKEN_SETTINGS, now=1000.0)
    with pytest.raises(DeletionTokenError):
        verify_deletion_token(token, settings=other, now=1000.0)


# ── Mailer unit tests (offline) ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logging_mailer_sends_nothing_and_does_not_raise() -> None:
    await LoggingMailer().send_account_deletion_link(
        to_email="a@example.com", confirm_url="https://x/delete-account?token=t"
    )  # no egress, no exception


def test_build_mailer_selects_logging_without_a_key_and_resend_with_one() -> None:
    assert isinstance(build_mailer(Settings(_env_file=None)), LoggingMailer)  # type: ignore[call-arg]
    with_key = Settings(_env_file=None, resend_api_key=SecretStr("re_test"))  # type: ignore[call-arg]
    assert isinstance(build_mailer(with_key), ResendMailer)


def test_get_mailer_dependency_returns_a_mailer() -> None:
    assert isinstance(get_mailer(), Mailer)


@pytest.mark.asyncio
async def test_resend_mailer_posts_to_resend_with_auth() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": "email_1"})

    mailer = ResendMailer(
        api_key="re_test",
        sender="Lengua <privacy@lengua.app>",
        transport=httpx.MockTransport(handler),
    )
    await mailer.send_account_deletion_link(
        to_email="user@example.com", confirm_url="https://lengua.app/delete-account?token=tok"
    )
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_test"


@pytest.mark.asyncio
async def test_resend_mailer_swallows_a_delivery_failure() -> None:
    """A 4xx/5xx from Resend must not raise (the endpoint's generic ack is returned regardless)."""
    mailer = ResendMailer(
        api_key="re_test",
        sender="x",
        transport=httpx.MockTransport(lambda _req: httpx.Response(422)),
    )
    await mailer.send_account_deletion_link(
        to_email="u@example.com", confirm_url="https://x?token=t"
    )


@pytest.mark.asyncio
async def test_resend_mailer_swallows_a_transport_error() -> None:
    """A raised transport error (Resend down) must NOT propagate — else it becomes a 500 oracle."""

    def boom(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("resend is down")

    mailer = ResendMailer(api_key="re_test", sender="x", transport=httpx.MockTransport(boom))
    await mailer.send_account_deletion_link(  # must not raise
        to_email="u@example.com", confirm_url="https://x?token=t"
    )


# ── Email → auth-user-id admin lookup unit tests (offline) ───────────────────────────────────────

_ADMIN = Settings(  # type: ignore[call-arg]
    _env_file=None,
    supabase_url="http://auth.test",
    supabase_service_role_key=SecretStr("service-role-test-key"),
)


def _users_page(handler_pages: list[list[dict[str, str]]]) -> httpx.MockTransport:
    """A transport that serves ``handler_pages[page-1]`` for the admin list-users GET."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        users = handler_pages[page - 1] if page - 1 < len(handler_pages) else []
        return httpx.Response(200, json={"users": users})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_find_user_by_email_returns_the_matching_id() -> None:
    uid = str(uuid.uuid4())
    svc = AccountDeletionService(
        _ADMIN, transport=_users_page([[{"id": uid, "email": "Found@Example.com"}]])
    )
    assert await svc.find_auth_user_id_by_email("found@example.com") == uuid.UUID(uid)


@pytest.mark.asyncio
async def test_find_user_by_email_paginates_until_found() -> None:
    uid = str(uuid.uuid4())
    full = [{"id": str(uuid.uuid4()), "email": f"u{i}@example.com"} for i in range(200)]
    svc = AccountDeletionService(
        _ADMIN, transport=_users_page([full, [{"id": uid, "email": "target@example.com"}]])
    )
    assert await svc.find_auth_user_id_by_email("target@example.com") == uuid.UUID(uid)


@pytest.mark.asyncio
async def test_find_user_by_email_returns_none_when_absent() -> None:
    svc = AccountDeletionService(_ADMIN, transport=_users_page([[]]))
    assert await svc.find_auth_user_id_by_email("nobody@example.com") is None


@pytest.mark.asyncio
async def test_find_user_by_email_returns_none_without_admin_credentials() -> None:
    svc = AccountDeletionService(Settings(_env_file=None))  # type: ignore[call-arg]
    assert await svc.find_auth_user_id_by_email("x@example.com") is None


@pytest.mark.asyncio
async def test_find_user_by_email_returns_none_on_admin_error() -> None:
    svc = AccountDeletionService(
        _ADMIN, transport=httpx.MockTransport(lambda _req: httpx.Response(500))
    )
    assert await svc.find_auth_user_id_by_email("x@example.com") is None


# ── Public endpoint unit tests (offline, ASGI with overrides) ────────────────────────────────────


class _FakeDeletion:
    """A stand-in deletion service: canned email lookup + a record of deleted ids."""

    def __init__(self, *, found_id: uuid.UUID | None = None) -> None:
        self._found_id = found_id
        self.deleted: list[uuid.UUID] = []

    async def find_auth_user_id_by_email(self, email: str) -> uuid.UUID | None:
        return self._found_id

    async def delete_user(self, user_id: uuid.UUID, *, db: object) -> None:
        self.deleted.append(user_id)


class _FailingDeletion(_FakeDeletion):
    async def delete_user(self, user_id: uuid.UUID, *, db: object) -> None:
        raise AccountAdminError("admin api unavailable")


class _SpyMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_account_deletion_link(self, *, to_email: str, confirm_url: str) -> None:
        self.sent.append((to_email, confirm_url))


class _RaisingMailer(Mailer):
    """A mailer whose send raises — proving the endpoint never leaks existence via a 500."""

    async def send_account_deletion_link(self, *, to_email: str, confirm_url: str) -> None:
        raise httpx.ConnectError("mail transport down")


async def _fake_usage_db() -> AsyncIterator[object]:
    yield object()


def _build_public_app(
    *,
    deletion: object,
    mailer: Mailer,
    limiter: InProcessRateLimiter | None = None,
    ip_limiter: InProcessRateLimiter | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Create the app with the public-deletion dependencies overridden for offline testing."""
    from app.deps import get_account_deletion_service, get_usage_db
    from app.mailer import get_mailer as _get_mailer
    from app.main import create_app
    from app.ratelimit import (
        get_public_deletion_ip_rate_limiter,
        get_public_deletion_rate_limiter,
    )
    from app.settings import get_settings as _get_settings

    app = create_app(include_test_routes=False)
    app.dependency_overrides[get_account_deletion_service] = lambda: deletion
    app.dependency_overrides[_get_mailer] = lambda: mailer
    app.dependency_overrides[get_usage_db] = _fake_usage_db
    app.dependency_overrides[get_public_deletion_rate_limiter] = lambda: (
        limiter or InProcessRateLimiter(limit=5, window_seconds=3600.0, clock=lambda: 0.0)
    )
    # A fresh, effectively-unbounded per-IP limiter by default so the process-wide singleton can't
    # bleed hits between tests (the per-IP test passes its own low-limit one).
    app.dependency_overrides[get_public_deletion_ip_rate_limiter] = lambda: (
        ip_limiter or InProcessRateLimiter(limit=1000, window_seconds=3600.0, clock=lambda: 0.0)
    )
    if settings is not None:
        app.dependency_overrides[_get_settings] = lambda: settings
    return app


@pytest.mark.asyncio
async def test_request_emails_a_verifiable_token_when_the_account_exists() -> None:
    user_id = uuid.uuid4()
    settings = Settings(_env_file=None, supabase_service_role_key=SecretStr("k"))  # type: ignore[call-arg]
    mailer = _SpyMailer()
    app = _build_public_app(
        deletion=_FakeDeletion(found_id=user_id), mailer=mailer, settings=settings
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-request", json={"email": "user@example.com"})
        assert resp.status_code == 200, resp.text
        assert "if an account exists" in resp.json()["message"].lower()
        assert len(mailer.sent) == 1
        _to, url = mailer.sent[0]
        token = url.split("token=", 1)[1]
        assert verify_deletion_token(token, settings=settings) == user_id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_request_gives_the_same_ack_and_sends_nothing_for_an_unknown_email() -> None:
    mailer = _SpyMailer()
    app = _build_public_app(deletion=_FakeDeletion(found_id=None), mailer=mailer)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-request", json={"email": "ghost@example.com"})
        assert resp.status_code == 200, resp.text
        assert (
            "if an account exists" in resp.json()["message"].lower()
        )  # identical, non-enumerating
        assert mailer.sent == []  # no email for a non-existent account
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_request_returns_generic_ack_even_when_mail_fails() -> None:
    """A registered address whose mail send RAISES still returns 200 + the generic ack."""
    settings = Settings(_env_file=None, supabase_service_role_key=SecretStr("k"))  # type: ignore[call-arg]
    app = _build_public_app(
        deletion=_FakeDeletion(found_id=uuid.uuid4()), mailer=_RaisingMailer(), settings=settings
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-request", json={"email": "user@example.com"})
        assert resp.status_code == 200, resp.text  # NOT a 500 — the mail failure is swallowed
        assert "if an account exists" in resp.json()["message"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_request_rejects_a_malformed_email() -> None:
    app = _build_public_app(deletion=_FakeDeletion(), mailer=_SpyMailer())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-request", json={"email": "not-an-email"})
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_request_is_rate_limited_per_email() -> None:
    limiter = InProcessRateLimiter(limit=2, window_seconds=3600.0, clock=lambda: 0.0)
    app = _build_public_app(
        deletion=_FakeDeletion(found_id=None), mailer=_SpyMailer(), limiter=limiter
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            body = {"email": "spammed@example.com"}
            assert (await c.post("/account/deletion-request", json=body)).status_code == 200
            assert (await c.post("/account/deletion-request", json=body)).status_code == 200
            third = await c.post("/account/deletion-request", json=body)
        assert third.status_code == 429, third.text
        assert third.headers.get("retry-after")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_request_is_rate_limited_per_ip_across_distinct_emails() -> None:
    """One source rotating through DISTINCT emails is capped per-IP. Each address is a fresh key for
    the per-email cap, so only the per-IP cap sees the flood; the ASGI client is one IP bucket."""
    ip_limiter = InProcessRateLimiter(limit=2, window_seconds=3600.0, clock=lambda: 0.0)
    app = _build_public_app(
        deletion=_FakeDeletion(found_id=None), mailer=_SpyMailer(), ip_limiter=ip_limiter
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            first = await c.post("/account/deletion-request", json={"email": "a@example.com"})
            second = await c.post("/account/deletion-request", json={"email": "b@example.com"})
            third = await c.post("/account/deletion-request", json={"email": "c@example.com"})
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert third.status_code == 429, third.text  # distinct email, but same source IP → capped
        assert third.headers.get("retry-after")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_confirm_deletes_the_account_for_a_valid_token() -> None:
    user_id = uuid.uuid4()
    settings = Settings(_env_file=None, supabase_service_role_key=SecretStr("k"))  # type: ignore[call-arg]
    deletion = _FakeDeletion()
    app = _build_public_app(deletion=deletion, mailer=_SpyMailer(), settings=settings)
    token = sign_deletion_token(user_id, settings=settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-confirm", json={"token": token})
        assert resp.status_code == 200, resp.text
        assert deletion.deleted == [user_id]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_confirm_rejects_an_invalid_token() -> None:
    app = _build_public_app(deletion=_FakeDeletion(), mailer=_SpyMailer())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-confirm", json={"token": "garbage.token"})
        assert resp.status_code == 400, resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_confirm_maps_a_backend_failure_to_502() -> None:
    user_id = uuid.uuid4()
    settings = Settings(_env_file=None, supabase_service_role_key=SecretStr("k"))  # type: ignore[call-arg]
    app = _build_public_app(deletion=_FailingDeletion(), mailer=_SpyMailer(), settings=settings)
    token = sign_deletion_token(user_id, settings=settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/account/deletion-confirm", json={"token": token})
        assert resp.status_code == 502, resp.text
    finally:
        app.dependency_overrides.clear()


# ── Integration: the real request → confirm → cascade flow against the live stack ────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_deletion_request_then_confirm_cascades() -> None:
    """End to end: request (real lookup) → emailed token → confirm removes A entirely; B intact."""
    from app.deps import get_usage_db
    from app.mailer import get_mailer as _get_mailer
    from app.main import create_app
    from app.ratelimit import (
        get_public_deletion_ip_rate_limiter,
        get_public_deletion_rate_limiter,
    )
    from app.settings import get_settings
    from tests.conftest import database_url
    from tests.supabase_auth import create_confirmed_user, delete_user
    from tests.test_account_delete import (
        _domain_counts,
        _fresh_usage_db,
        _real_stack_settings,
        _seed_committed_graph,
    )

    with httpx.Client(timeout=30.0) as http:
        user_a = create_confirmed_user(http, email=f"pub-del-a-{uuid.uuid4().hex[:8]}@lengua.test")
        user_b = create_confirmed_user(http, email=f"pub-del-b-{uuid.uuid4().hex[:8]}@lengua.test")
        try:
            _seed_committed_graph(user_a.id, "A-Spanish")
            _seed_committed_graph(user_b.id, "B-French")

            spy = _SpyMailer()
            app = create_app(include_test_routes=False)
            app.dependency_overrides[get_settings] = _real_stack_settings
            app.dependency_overrides[_get_mailer] = lambda: spy
            app.dependency_overrides[get_usage_db] = _fresh_usage_db
            app.dependency_overrides[get_public_deletion_rate_limiter] = lambda: (
                InProcessRateLimiter(limit=5, window_seconds=3600.0)
            )
            app.dependency_overrides[get_public_deletion_ip_rate_limiter] = lambda: (
                InProcessRateLimiter(limit=1000, window_seconds=3600.0)
            )
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                    # 1. Request: the real Auth Admin lookup resolves A's email and mails a token.
                    req = await client.post(
                        "/account/deletion-request", json={"email": user_a.email}
                    )
                    assert req.status_code == 200, req.text
                    assert len(spy.sent) == 1, "a confirmation email should have been sent for A"
                    token = spy.sent[0][1].split("token=", 1)[1]

                    # 2. Confirm: verifying the token runs the real cascade delete.
                    confirm = await client.post("/account/deletion-confirm", json={"token": token})
                    assert confirm.status_code == 200, confirm.text
            finally:
                app.dependency_overrides.clear()

            # A is gone everywhere (auth.users + every domain table); B is untouched.
            with psycopg.connect(database_url()) as conn:
                auth_a = conn.execute(
                    "SELECT count(*) FROM auth.users WHERE id = %s", (user_a.id,)
                ).fetchone()
                assert auth_a is not None and auth_a[0] == 0, "A's auth.users row must be gone"
                after_a = _domain_counts(conn, user_a.id)
                assert after_a == {k: 0 for k in after_a}, f"A left orphan rows: {after_a}"
                after_b = _domain_counts(conn, user_b.id)
                assert all(v >= 1 for v in after_b.values()), f"B must be untouched: {after_b}"
        finally:
            delete_user(http, user_a.id)  # already gone (404 tolerated) — defensive
            delete_user(http, user_b.id)  # cascades B's committed graph away


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_deletion_request_for_unknown_email_sends_nothing() -> None:
    """A deletion request for a non-existent address returns the generic ack and emails no one."""
    from app.deps import get_usage_db
    from app.mailer import get_mailer as _get_mailer
    from app.main import create_app
    from app.ratelimit import (
        get_public_deletion_ip_rate_limiter,
        get_public_deletion_rate_limiter,
    )
    from app.settings import get_settings
    from tests.test_account_delete import _fresh_usage_db, _real_stack_settings

    spy = _SpyMailer()
    app = create_app(include_test_routes=False)
    app.dependency_overrides[get_settings] = _real_stack_settings
    app.dependency_overrides[_get_mailer] = lambda: spy
    app.dependency_overrides[get_usage_db] = _fresh_usage_db
    app.dependency_overrides[get_public_deletion_rate_limiter] = lambda: InProcessRateLimiter(
        limit=5, window_seconds=3600.0
    )
    app.dependency_overrides[get_public_deletion_ip_rate_limiter] = lambda: InProcessRateLimiter(
        limit=1000, window_seconds=3600.0
    )
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/account/deletion-request",
                json={"email": f"nobody-{uuid.uuid4().hex[:8]}@lengua.test"},
            )
        assert resp.status_code == 200, resp.text
        assert spy.sent == []
    finally:
        app.dependency_overrides.clear()
