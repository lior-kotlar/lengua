"""Account-lifecycle router: data export + hard account deletion (task 2.8).

Two store-compliance / GDPR endpoints, both deriving the target user **solely** from the verified
JWT (``current_user``) — neither takes a user-id parameter, so a caller can only ever export or
delete *their own* account (task 2.8.4):

* ``GET /account/export`` — a downloadable JSON bundle of everything the user owns (profile,
  languages, cards, reviews, proficiency, settings), scoped to ``current_user`` (task 2.8.1).
* ``DELETE /account`` — hard-deletes the authenticated user with a two-step erasure
  (:class:`~app.services.account.AccountDeletionService`): it removes the ``profiles`` row (which
  cascades all domain data) on a privileged session, then deletes the Supabase ``auth.users`` row
  via the service-role Admin API (task 2.8.3). Returns ``204``.

**Deletion ordering / transactionality (S1 fix).** Erasure runs in two destructive steps:
**(1)** delete the ``profiles`` row on a privileged, RLS-bypassing session (``get_usage_db``) —
cascading languages/cards/reviews/proficiency/user_settings/llm_usage away via the
``… → profiles`` ``on delete cascade`` FKs — then **(2)** delete the ``auth.users`` row via the
Auth Admin API. Domain data is erased *first* on purpose: the load-bearing right-to-erasure
guarantee must hold even on a database missing the ``profiles → auth.users`` FK (the S1 bug, where
the Auth-only delete cascaded nothing and orphaned all domain data while returning ``204``), so if
the later auth-delete fails the user is still left with **no orphaned content**. Both steps are
idempotent (re-deleting an absent profile / an already-gone auth user is a no-op), so a partial
failure surfaces a ``502`` and the caller simply retries to completion — never a false ``204``.
After step 2 GoTrue revokes the user's refresh tokens, so the session cannot be renewed; the
short-lived access token is stateless and simply expires.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.db.session import UsageSession
from app.deps import (
    get_account_deletion_service,
    get_current_user,
    get_db,
    get_usage_db,
)
from app.schemas.account import AccountExport
from app.services.account import AccountAdminError, AccountDeletionService, ExportService

router = APIRouter(tags=["account"])


@router.get("/account/export", response_model=AccountExport)
async def export_account(
    response: Response,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountExport:
    """Return the authenticated user's full data bundle (scoped to ``current_user``)."""
    response.headers["Content-Disposition"] = 'attachment; filename="lengua-export.json"'
    return await ExportService(db).export(user.id)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    deletion: Annotated[AccountDeletionService, Depends(get_account_deletion_service)],
    usage_db: Annotated[UsageSession, Depends(get_usage_db)],
) -> Response:
    """Hard-delete the authenticated user's account (auth user + cascaded domain data)."""
    # NB: the one-line docstring above is the OpenAPI operation *description* (the contract the TS
    # client is generated from), so it is kept verbatim to avoid a schema regen. The two-step
    # ordering rationale lives in the module docstring. ``usage_db`` is the privileged,
    # RLS-bypassing session the service uses to hard-delete the ``profiles`` row (cascading all
    # domain data) before the auth-user delete.
    try:
        await deletion.delete_user(user.id, db=usage_db)
    except AccountAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Account deletion did not complete. Please retry.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
