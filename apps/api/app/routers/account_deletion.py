"""Public, unauthenticated account-deletion request/confirm endpoints (Phase 8, task 8.3.1).

Google Play requires a way to request account deletion that is reachable **without installing the
app or signing in**, and Apple requires in-app deletion (``DELETE /account``). This router is the
external half: the two public endpoints behind the ``/delete-account`` web form.

* ``POST /account/deletion-request`` — takes an email, and *if* it matches a Supabase Auth account,
  emails a confirmation link carrying a signed, one-hour token (:mod:`app.deletion_tokens`). It
  **always** returns the same generic acknowledgement (never disclosing whether the email is
  registered — no account enumeration) and is rate-limited per address to prevent inbox-bombing.
* ``POST /account/deletion-confirm`` — takes the signed token from that emailed link, verifies it,
  and runs the **exact same** two-step cascade delete as the in-app flow
  (:meth:`app.services.account.AccountDeletionService.delete_user` on a privileged session): erase
  all domain rows, then remove the Supabase ``auth.users`` record.

Both are intentionally public (no ``get_current_user``): ownership is proven by possession of the
emailed token, not a session. They are explicitly exempted from the "every route needs a JWT" /
"no anonymous writes" guards (``tests/test_routes_auth.py`` / ``tests/test_no_guest.py``), the same
way ``GET /feature-flags`` is.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.session import UsageSession
from app.deletion_tokens import DeletionTokenError, sign_deletion_token, verify_deletion_token
from app.deps import get_account_deletion_service, get_usage_db
from app.mailer import Mailer, get_mailer
from app.ratelimit import RateLimiter, get_public_deletion_rate_limiter
from app.schemas.account import (
    AccountDeletionAck,
    AccountDeletionConfirm,
    AccountDeletionRequest,
)
from app.services.account import AccountAdminError, AccountDeletionService
from app.settings import Settings, get_settings

logger = logging.getLogger("lengua.account_deletion")

router = APIRouter(tags=["account-deletion"])

#: Stable namespace for deriving the rate-limit key from an email (the limiter is keyed by UUID).
_EMAIL_RATE_KEY_NS = uuid.UUID("6f9b1e2c-0d3a-4c5b-9e8f-1a2b3c4d5e6f")

#: The single generic response — identical whether or not the email maps to an account.
_REQUEST_ACK = (
    "If an account exists for that email, we've sent a message with a link to confirm and "
    "complete the deletion. The link expires in one hour."
)
_CONFIRM_ACK = "Your account and all associated data have been permanently deleted."


def _deletion_confirm_url(settings: Settings, token: str) -> str:
    """Build the emailed link: ``<web>/delete-account?token=...`` (relative when no host is set)."""
    base = (settings.public_web_url or "").rstrip("/")
    return f"{base}/delete-account?token={token}"


@router.post("/account/deletion-request", response_model=AccountDeletionAck)
async def request_account_deletion(
    payload: AccountDeletionRequest,
    deletion: Annotated[AccountDeletionService, Depends(get_account_deletion_service)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
    limiter: Annotated[RateLimiter, Depends(get_public_deletion_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountDeletionAck:
    """Start a public account deletion: email a confirmation link if the address has an account.

    Always returns the same generic acknowledgement (no account enumeration). Rate-limited per email
    to prevent using the form to bomb an inbox with deletion mail.
    """
    email = payload.email.strip().lower()

    decision = limiter.hit(uuid.uuid5(_EMAIL_RATE_KEY_NS, email))
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many deletion requests for this email. Please try again later.",
            headers={"Retry-After": str(decision.retry_after)},
        )

    user_id = await deletion.find_auth_user_id_by_email(email)
    if user_id is not None:
        token = sign_deletion_token(user_id, settings=settings)
        # Belt-and-suspenders around the non-enumeration contract: even if a mailer raised, the
        # response must stay the generic ack (a 500 only for registered addresses would leak
        # existence). ResendMailer already swallows its own failures; this guards any mailer impl.
        try:
            await mailer.send_account_deletion_link(
                to_email=email, confirm_url=_deletion_confirm_url(settings, token)
            )
        except Exception:  # noqa: BLE001 — a mail failure must never become an existence oracle
            logger.warning("account-deletion confirmation mail could not be sent")
    return AccountDeletionAck(status="ok", message=_REQUEST_ACK)


@router.post("/account/deletion-confirm", response_model=AccountDeletionAck)
async def confirm_account_deletion(
    payload: AccountDeletionConfirm,
    deletion: Annotated[AccountDeletionService, Depends(get_account_deletion_service)],
    usage_db: Annotated[UsageSession, Depends(get_usage_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountDeletionAck:
    """Complete a public account deletion: verify the emailed token, then cascade-delete the user.

    A malformed / tampered / expired token → ``400`` (a generic "invalid or expired" message, never
    distinguishing which). A verified token runs the same hard delete as ``DELETE /account``; a
    backend failure surfaces ``502`` (retryable), never a false success.
    """
    try:
        user_id = verify_deletion_token(payload.token, settings=settings)
    except DeletionTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This deletion link is invalid or has expired. Please request a new one.",
        ) from exc

    try:
        await deletion.delete_user(user_id, db=usage_db)
    except AccountAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Account deletion did not complete. Please retry.",
        ) from exc

    return AccountDeletionAck(status="ok", message=_CONFIRM_ACK)
