"""Settings router (task 1.5.9): read and upsert the user's key/value preferences.

``GET /settings`` returns the full ``{key: value}`` map; ``PUT /settings`` merges the supplied keys
(a ``null`` value removes a key — finding S10) and returns the updated map, all scoped to
``current_user``. Out-of-bounds typed-numeric values and a ``daily_new_limit > daily_total_limit``
cross-field violation (finding S9) are rejected with **422** by the service layer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import current_user, get_db
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services.errors import ValidationError
from app.services.settings import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsOut:
    """Return all of the current user's settings."""
    values = await SettingsService(db).get_all(user_id)
    return SettingsOut(values=values)


@router.put("", response_model=SettingsOut)
async def put_settings(
    body: SettingsUpdate,
    user_id: uuid.UUID = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SettingsOut:
    """Upsert (merge) the supplied settings and return the full updated map."""
    service = SettingsService(db)
    try:
        await service.set_many(user_id, body.values)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return SettingsOut(values=await service.get_all(user_id))
