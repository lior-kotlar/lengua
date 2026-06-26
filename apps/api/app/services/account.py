"""Account-lifecycle services: data export and hard account deletion (task 2.8).

Two independent concerns, kept as separate classes because they touch different resources:

* :class:`ExportService` reads the **database** (scoped to one ``user_id``) and assembles the
  :class:`~app.schemas.account.AccountExport` bundle — profile, languages, cards, reviews,
  proficiency, and settings. Like every read path it goes through the repositories (the only
  SQL-touching layer) and never another user's rows.

* :class:`AccountDeletionService` deletes the user from **Supabase Auth** via the service-role
  *Admin API* (``DELETE /auth/v1/admin/users/{id}``). Because the canonical schema declares
  ``profiles.id references auth.users(id) on delete cascade`` (and every domain table cascades
  from ``profiles`` in turn), removing the ``auth.users`` row atomically cascades the profile and
  all domain data away in a single Postgres transaction inside GoTrue — there is no app-side
  multi-step write to leave a partial state. See ``app/routers/account.py`` for the ordering
  rationale (auth-user delete is the single, last, irreversible step, so a failure deletes
  nothing and the caller can safely retry).

The Admin API requires the **service-role key**, which is a server-only secret (``settings``) and
never reaches the client. ``current_user.id`` (from the verified JWT) is the only id ever passed,
so a user can only delete *themselves*.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.repositories.profiles import ProfilesRepository
from app.repositories.reviews import ReviewsRepository
from app.repositories.settings import SettingsRepository
from app.schemas.account import (
    AccountExport,
    CardExport,
    LanguageExport,
    ProficiencyExport,
    ProfileExport,
    ReviewExport,
)
from app.settings import Settings

#: Status codes from the Auth Admin delete we treat as success: ``200``/``204`` = deleted now,
#: ``404`` = the user is already gone (idempotent — the desired end state already holds).
_DELETE_OK = frozenset({200, 204, 404})


class AccountAdminError(RuntimeError):
    """The Supabase Auth Admin API call failed (the router maps this to HTTP ``502``)."""


class ExportService:
    """Assemble the full data-export bundle for a single user, scoped to ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._profiles = ProfilesRepository(session)
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._reviews = ReviewsRepository(session)
        self._proficiency = ProficiencyRepository(session)
        self._settings = SettingsRepository(session)

    async def export(self, user_id: uuid.UUID) -> AccountExport:
        """Return every row owned by ``user_id`` as an :class:`AccountExport` bundle."""
        profile = await self._profiles.get(user_id)
        return AccountExport(
            profile=ProfileExport.model_validate(profile) if profile is not None else None,
            languages=[
                LanguageExport.model_validate(row)
                for row in await self._languages.list_for_user(user_id)
            ],
            cards=[
                CardExport.model_validate(row) for row in await self._cards.list_for_user(user_id)
            ],
            reviews=[
                ReviewExport.model_validate(row)
                for row in await self._reviews.list_for_user(user_id)
            ],
            proficiency=[
                ProficiencyExport.model_validate(row)
                for row in await self._proficiency.list_for_user(user_id)
            ],
            settings=dict(await self._settings.get_all(user_id)),
        )


class AccountDeletionService:
    """Hard-delete a user from Supabase Auth via the service-role Admin API.

    Deleting the ``auth.users`` row cascades the ``profiles`` row and all domain data away in one
    atomic step (FK ``on delete cascade``). A custom ``transport`` is injectable so unit tests can
    drive the Admin call with an offline :class:`httpx.MockTransport` (no network).
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Admin-delete ``user_id`` from ``auth.users`` (cascading every owned row).

        Fails closed (:class:`AccountAdminError`) if the Supabase URL / service-role key are not
        configured — we never attempt a privileged deletion without real admin credentials. A
        non-success, non-404 response from GoTrue is surfaced as :class:`AccountAdminError`.
        """
        base_url = (self._settings.supabase_url or "").rstrip("/")
        service_key = self._settings.supabase_service_role_key.get_secret_value()
        if not base_url or not service_key:
            raise AccountAdminError("Supabase admin credentials are not configured")

        url = f"{base_url}/auth/v1/admin/users/{user_id}"
        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                # Send ``should_soft_delete=false`` EXPLICITLY rather than leaning on GoTrue's
                # implicit default: this is the single most GDPR-load-bearing line in the app, so a
                # hard delete (which fires the ``auth.users → profiles → domain`` FK cascade) must
                # not be silently flippable to a soft delete by an upstream default change.
                # ``httpx.AsyncClient.delete`` takes no body, so use the generic ``request``.
                response = await client.request(
                    "DELETE", url, headers=headers, json={"should_soft_delete": False}
                )
        except httpx.HTTPError as exc:  # network/timeout — nothing was deleted, safe to retry
            raise AccountAdminError(f"auth admin request failed: {exc}") from exc

        if response.status_code not in _DELETE_OK:
            raise AccountAdminError(f"auth admin delete returned {response.status_code}")
