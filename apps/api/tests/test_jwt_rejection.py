"""Malicious-token rejection tests (task 2.3.3) — at both the verifier and the HTTP layer.

Asserts the three classic forgeries are rejected: an expired token, a token re-signed with the
wrong key, and a hand-crafted ``{"alg":"none"}`` token. Each is checked directly against
:func:`app.auth.decode_supabase_jwt` (``AuthError``) and end-to-end against ``GET /me`` (HTTP 401).
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import AuthError, decode_supabase_jwt
from app.main import create_app
from tests.auth_helpers import (
    TEST_AUDIENCE,
    install_test_auth,
    make_supabase_jwt,
    make_test_settings,
)

USER_ID = "9c2b1a0d-3e4f-5a6b-7c8d-9e0f1a2b3c4d"


def _expired_token() -> str:
    return make_supabase_jwt(
        USER_ID, issued_at=datetime.now(tz=UTC) - timedelta(days=1), expires_in=3600
    )


def _wrong_key_token() -> str:
    return make_supabase_jwt(USER_ID, secret="attacker-controlled-secret-key-000000000")


def _alg_none_token() -> str:
    """Hand-craft an unsigned ``alg:none`` token (the empty third segment = no signature)."""

    def _seg(obj: dict[str, object]) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = _seg({"alg": "none", "typ": "JWT"})
    exp = int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp())
    payload = _seg({"sub": USER_ID, "aud": TEST_AUDIENCE, "exp": exp})
    return f"{header}.{payload}."


@pytest.mark.parametrize(
    "token_factory",
    [_expired_token, _wrong_key_token, _alg_none_token],
    ids=["expired", "wrong-key", "alg-none"],
)
def test_verifier_rejects_malicious_token(token_factory: object) -> None:
    token = token_factory()  # type: ignore[operator]
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token_factory",
    [_expired_token, _wrong_key_token, _alg_none_token],
    ids=["expired", "wrong-key", "alg-none"],
)
async def test_me_rejects_malicious_token_with_401(token_factory: object) -> None:
    app = create_app()
    install_test_auth(app)
    token = token_factory()  # type: ignore[operator]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
