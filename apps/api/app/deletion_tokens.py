"""Signed, self-expiring account-deletion tokens (Phase 8, task 8.3.1).

The public ``/delete-account`` form must let someone erase their account **without signing in**
(Google Play requires an externally-reachable deletion path), which means we cannot rely on a JWT
to prove who is asking. Ownership is instead proven *out of band*: a deletion **request** mints one
of these tokens for the account and emails a confirmation link carrying it; clicking the link
(``POST /account/deletion-confirm``) verifies the token and runs the exact same cascade delete as
the in-app flow. Only the person who can read the account's inbox ever receives the token, so
possession of a valid token **is** proof of email ownership.

The token is a stateless HMAC over ``(user_id, expiry)`` — unforgeable without the server key and
self-expiring, so there is no server-side table of pending deletions to store, leak, or clean up.
The signing key is *derived* from the Supabase service-role secret (server-only, and present exactly
where a deletion can actually run) via a one-way hash with a context label, so the raw admin key is
never used directly as the token key and the token key can't be reversed back into it.

Security properties:

* **Unforgeable.** Without the derived key an attacker cannot produce a valid ``(user_id, exp)``
  signature, so they cannot mint a deletion token for a victim's account.
* **Non-enumerating.** The request endpoint never returns the token (it is only emailed), so the
  only way to obtain a valid token is to control the target inbox.
* **Short-lived.** A token is valid for :data:`DELETION_TOKEN_TTL_SECONDS`; an intercepted stale
  link cannot be replayed later.
* **Constant-time compare.** Signature verification uses :func:`hmac.compare_digest`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

from app.settings import Settings

#: How long a freshly-minted deletion token stays valid (seconds). One hour balances "long enough to
#: click the emailed link" against "short enough that an intercepted stale link is useless".
DELETION_TOKEN_TTL_SECONDS = 3600

#: Domain-separation label folded into the key derivation so this token key can never collide with
#: any other use of the service-role secret.
_KEY_CONTEXT = b"lengua:account-deletion-token:v1"


class DeletionTokenError(ValueError):
    """The deletion token is malformed, tampered with, or expired (never distinguished)."""


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding (compact + safe in a query string / email link)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    """Inverse of :func:`_b64encode`, restoring the stripped ``=`` padding."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _signing_key(settings: Settings) -> bytes:
    """Derive the HMAC key from the service-role secret (one-way; never the raw key itself).

    Deriving rather than using the raw admin key means the token key is domain-separated and cannot
    be reversed into the admin key. When the service-role key is unset (the local/CI/unit path) this
    still returns a stable key so sign/verify round-trips in tests — but a token is only ever
    *actioned* where a deletion can run (which requires the real admin key), so a token derived from
    an empty secret is harmless.
    """
    secret = settings.supabase_service_role_key.get_secret_value().encode("utf-8")
    return hashlib.sha256(_KEY_CONTEXT + b":" + secret).digest()


def sign_deletion_token(
    user_id: uuid.UUID,
    *,
    settings: Settings,
    now: float | None = None,
    ttl_seconds: int = DELETION_TOKEN_TTL_SECONDS,
) -> str:
    """Mint a signed, expiring deletion token for ``user_id``.

    ``now`` is injectable so tests are deterministic; production passes the wall clock.
    """
    issued = int(now if now is not None else time.time())
    payload = f"{user_id}:{issued + ttl_seconds}".encode("ascii")
    signature = hmac.new(_signing_key(settings), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def verify_deletion_token(token: str, *, settings: Settings, now: float | None = None) -> uuid.UUID:
    """Return the ``user_id`` a valid token authorizes, else raise ``DeletionTokenError``.

    Raises for a malformed token, a bad/tampered signature, or an expired token — the caller maps
    all of these to one generic "invalid or expired link" response (they are never distinguished).
    """
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _b64decode(payload_b64)
        signature = _b64decode(signature_b64)
    except (ValueError, TypeError) as exc:
        raise DeletionTokenError("malformed deletion token") from exc

    expected = hmac.new(_signing_key(settings), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise DeletionTokenError("bad deletion-token signature")

    try:
        user_part, exp_part = payload.decode("ascii").split(":", 1)
        user_id = uuid.UUID(user_part)
        expires_at = int(exp_part)
    except (ValueError, TypeError) as exc:
        raise DeletionTokenError("unreadable deletion-token payload") from exc

    if (now if now is not None else time.time()) > expires_at:
        raise DeletionTokenError("expired deletion token")
    return user_id
