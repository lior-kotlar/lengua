"""Account-lifecycle router: data export + hard account deletion (task 2.8).

Two store-compliance / GDPR endpoints, both deriving the target user **solely** from the verified
JWT (``current_user``) — neither takes a user-id parameter, so a caller can only ever export or
delete *their own* account (task 2.8.4):

* ``GET /account/export`` — a downloadable JSON bundle of everything the user owns (profile,
  languages, cards, reviews, proficiency, settings), scoped to ``current_user`` (task 2.8.1).
* ``DELETE /account`` — hard-deletes the authenticated user's Supabase ``auth.users`` row via the
  service-role Admin API, which cascades the ``profiles`` row and all domain data away atomically
  (task 2.8.3). Returns ``204``.

**Deletion ordering / transactionality.** The single irreversible step — the Auth Admin
``DELETE`` — is the *only* destructive action and runs *last*, so if it fails nothing has been
removed and the caller can retry safely (no partial state). We deliberately do **not** delete the
``profiles`` row app-side first: that would be redundant (the ``auth.users``→``profiles``→domain
``on delete cascade`` already removes it in one transaction) and, if it ran before a failing Admin
call, would orphan the auth user (logged-in but data-less). After deletion GoTrue also revokes the
user's refresh tokens, so the session cannot be renewed; the short-lived access token is stateless
and simply expires.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.deps import get_account_deletion_service, get_current_user, get_db
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
) -> Response:
    """Hard-delete the authenticated user's account (auth user + cascaded domain data)."""
    try:
        await deletion.delete_user(user.id)
    except AccountAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Account deletion failed; no data was removed. Please retry.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
