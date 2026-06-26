"""JWT verification unit tests (task 2.3.1) — pure, no DB/network.

Proves :func:`app.auth.decode_supabase_jwt` validates signature, ``exp`` and ``aud`` and returns
the correct identity, for both the HS256 (shared-secret) and RS256 (JWKS) signing schemes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient

from app.auth import AuthError, CurrentUser, decode_supabase_jwt
from app.settings import Settings
from tests.auth_helpers import TEST_JWT_SECRET, make_supabase_jwt, make_test_settings

USER_ID = "3f1c8d2e-7b6a-4c5d-9e0f-1a2b3c4d5e6f"


def test_valid_token_yields_correct_sub() -> None:
    user = decode_supabase_jwt(make_supabase_jwt(USER_ID), settings=make_test_settings())
    assert isinstance(user, CurrentUser)
    assert user.id == uuid.UUID(USER_ID)
    assert user.email_verified is True
    assert user.email == "user@example.com"


def test_email_verified_false_propagates() -> None:
    token = make_supabase_jwt(USER_ID, email_verified=False)
    user = decode_supabase_jwt(token, settings=make_test_settings())
    assert user.email_verified is False


def test_wrong_audience_is_rejected() -> None:
    token = make_supabase_jwt(USER_ID, audience="some-other-aud")
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_signature_is_checked() -> None:
    # A token signed with a different secret must not verify against the configured secret.
    token = make_supabase_jwt(USER_ID, secret="a-totally-different-secret-key-987654321")
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_expiry_is_checked() -> None:
    token = make_supabase_jwt(
        USER_ID, issued_at=datetime.now(tz=UTC) - timedelta(hours=2), expires_in=3600
    )
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_missing_sub_is_rejected() -> None:
    # Omit `sub` entirely — PyJWT's `require` rejects it before identity extraction.
    now = int(datetime.now(tz=UTC).timestamp())
    token = jwt.encode(
        {"aud": "authenticated", "exp": now + 3600}, TEST_JWT_SECRET, algorithm="HS256"
    )
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_blank_sub_is_rejected() -> None:
    # A present-but-empty `sub` passes `require` but is caught by the identity guard.
    token = make_supabase_jwt("")
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_non_uuid_sub_is_rejected() -> None:
    token = make_supabase_jwt("not-a-uuid")
    with pytest.raises(AuthError, match="UUID"):
        decode_supabase_jwt(token, settings=make_test_settings())


def test_empty_secret_fails_closed() -> None:
    token = make_supabase_jwt(USER_ID)
    settings = Settings(_env_file=None, supabase_jwt_secret="", supabase_jwks_url="")  # type: ignore[call-arg]
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=settings)


def test_rs256_token_verified_via_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a JWKS URL is configured, an RS256 token verifies against the fetched public key."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = datetime.now(tz=UTC)
    token = jwt.encode(
        {
            "sub": USER_ID,
            "aud": "authenticated",
            "email": "rs@example.com",
            "email_verified": True,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
    )

    class _SigningKey:
        key = private_key.public_key()

    # Avoid any network: the JWKS client returns our locally generated public key.
    monkeypatch.setattr(
        PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, _token: _SigningKey(),
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwks_url="https://example.test/.well-known/jwks.json",
        supabase_jwt_secret="",
    )
    user = decode_supabase_jwt(token, settings=settings)
    assert user.id == uuid.UUID(USER_ID)
    assert user.email == "rs@example.com"


def test_hs256_token_rejected_when_jwks_expects_asymmetric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Algorithm-confusion guard: an HS256 token is not accepted on the RS256/ES256 JWKS path."""
    token = make_supabase_jwt(USER_ID)

    class _SigningKey:
        # Even handed the (wrong-type) public key, the HS256 alg is not in the allow-list.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()

    monkeypatch.setattr(
        PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, _token: _SigningKey(),
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwks_url="https://example.test/.well-known/jwks.json",
        supabase_jwt_secret="",
    )
    with pytest.raises(AuthError):
        decode_supabase_jwt(token, settings=settings)
