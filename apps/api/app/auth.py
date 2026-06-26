"""Supabase JWT verification (task 2.3.1).

FastAPI must verify the Supabase access token on every request and **never** trust a
client-supplied user id. :func:`decode_supabase_jwt` validates the token's *signature*, *expiry*
(``exp``) and *audience* (``aud``) and returns a typed :class:`CurrentUser` carrying the user id
(the UUID in the ``sub`` claim) and ``email_verified``.

Two signing schemes are supported, selected by configuration:

* **HS256 + shared secret** (the default and what the Supabase CLI / legacy projects issue) — the
  token is verified with ``settings.supabase_jwt_secret``.
* **RS256/ES256 + JWKS** (Supabase's asymmetric "JWT signing keys") — when
  ``settings.supabase_jwks_url`` is set, the verifying public key is fetched from that JWKS
  endpoint (cached per URL).

The set of accepted algorithms is fixed by *configuration*, never read from the attacker-controlled
token header, so ``alg: none`` and HS/RS "algorithm-confusion" forgeries are rejected: an
unexpected ``alg`` is simply not in the allow-list. Every verification failure is surfaced as a
single :class:`AuthError`, which the dependency layer (:mod:`app.deps`) maps to HTTP ``401`` — we
never leak the underlying reason to the caller.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict

from app.settings import Settings

#: Supabase issues access tokens with ``aud = "authenticated"`` for signed-in users.
DEFAULT_AUDIENCE = "authenticated"

_HS256 = "HS256"
#: Asymmetric algorithms accepted on the JWKS path (Supabase signing keys are RSA or ECC).
_ASYMMETRIC_ALGS = ("RS256", "ES256")


class AuthError(Exception):
    """A bearer token failed verification (mapped to HTTP 401 by :mod:`app.deps`)."""


class CurrentUser(BaseModel):
    """The verified identity extracted from a Supabase access token.

    Only ever constructed from a signature-verified JWT — never from client-supplied fields.
    ``id`` is the user's UUID (the token ``sub``); ``email_verified`` gates email-required actions
    (e.g. the Phase 3 LLM quota check).
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    email: str | None = None
    email_verified: bool = False


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    """Return a process-cached :class:`PyJWKClient` for ``url`` (it memoizes fetched keys)."""
    return PyJWKClient(url)


def _identity_from_claims(claims: dict[str, Any]) -> CurrentUser:
    """Build a :class:`CurrentUser` from verified JWT claims (validates ``sub`` is a UUID)."""
    sub = claims.get("sub")
    if not sub:
        raise AuthError("token is missing the `sub` claim")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, AttributeError, TypeError) as exc:
        raise AuthError("token `sub` is not a valid UUID") from exc

    metadata = claims.get("user_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    email_verified = bool(claims.get("email_verified", metadata.get("email_verified", False)))
    email = claims.get("email") or metadata.get("email")
    return CurrentUser(id=user_id, email=email, email_verified=email_verified)


def _resolve_key_and_algorithms(token: str, settings: Settings) -> tuple[Any, list[str]]:
    """Pick the verifying key + the allow-listed algorithms from configuration (never the token).

    JWKS mode -> the public key fetched for this token + RS256/ES256; otherwise the HS256 shared
    secret. The algorithm set is fixed here, so ``alg: none`` / HS-vs-RS confusion can never slip a
    forged token through.
    """
    if settings.supabase_jwks_url:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return signing_key.key, list(_ASYMMETRIC_ALGS)
    if not settings.supabase_jwt_secret:
        # Fail closed: never verify an HS256 token against an empty secret.
        raise AuthError("SUPABASE_JWT_SECRET is not configured")
    return settings.supabase_jwt_secret, [_HS256]


def decode_supabase_jwt(token: str, *, settings: Settings) -> CurrentUser:
    """Verify a Supabase JWT (signature + ``exp`` + ``aud``) and return the typed identity.

    Raises :class:`AuthError` on any failure: bad/forged signature, expired token, wrong audience,
    a disallowed/``none`` algorithm, a missing/non-UUID ``sub``, or (JWKS mode) an unresolvable
    signing key.
    """
    audience = settings.supabase_jwt_aud or DEFAULT_AUDIENCE
    try:
        key, algorithms = _resolve_key_and_algorithms(token, settings)
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=audience,
            # `require` makes a token missing exp/sub/aud invalid rather than silently trusted.
            options={"require": ["exp", "sub", "aud"], "verify_aud": True},
        )
    except jwt.PyJWTError as exc:  # signature/exp/aud/alg/JWKS failures all subclass this
        raise AuthError(f"token rejected: {type(exc).__name__}") from exc

    return _identity_from_claims(claims)
