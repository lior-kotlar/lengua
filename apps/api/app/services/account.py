"""Account-lifecycle services: data export and hard account deletion (task 2.8).

Two independent concerns, kept as separate classes because they touch different resources:

* :class:`ExportService` reads the **database** (scoped to one ``user_id``) and assembles the
  :class:`~app.schemas.account.AccountExport` bundle — profile, languages, cards, reviews,
  proficiency, and settings. Like every read path it goes through the repositories (the only
  SQL-touching layer) and never another user's rows.

* :class:`AccountDeletionService` hard-deletes the user with a two-step, defense-in-depth erasure:
  (1) it deletes the user's ``profiles`` row on a **privileged, RLS-bypassing** DB session — which
  cascades every domain row (languages/cards/reviews/proficiency/user_settings/llm_usage) away via
  the ``… → profiles(id) on delete cascade`` FKs — and then (2) deletes the **Supabase Auth** user
  via the service-role *Admin API* (``DELETE /auth/v1/admin/users/{id}``), which revokes the
  refresh tokens and removes the ``auth.users`` row. Step 1 is what makes erasure correct *even on
  a database missing the* ``profiles → auth.users`` *FK* — the S1 bug: staging/prod were built by
  the Alembic chain, which lacked that FK (migration ``0006`` adds it back), so the Auth-only
  delete cascaded nothing and orphaned all domain data while still returning ``204``. On a DB that
  *does* have the FK, step 2's cascade simply re-deletes an already-gone profile — harmless. See
  ``app/routers/account.py`` for the ordering rationale (domain data erased first, so a failure of
  the later auth-delete still leaves no orphaned user content; both steps are idempotent, so a
  retry safely completes).

The Admin API requires the **service-role key**, which is a server-only secret (``settings``) and
never reaches the client. ``current_user.id`` (from the verified JWT) is the only id ever passed,
so a user can only delete *themselves*.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import delete as sql_delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Profile
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

#: Admin "list users" pagination (used to resolve an email → auth-user id for the public deletion
#: form). ``per_page`` is GoTrue's max; the page cap bounds a pathological scan (100 * 200 = 20k
#: users) so a lookup can never spin unbounded — far above the expected user count for v1.
_ADMIN_USERS_PER_PAGE = 200
_ADMIN_USERS_MAX_PAGES = 100


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
    """Hard-delete a user: erase their domain data, then their Supabase Auth identity.

    Two steps, in this order (defense-in-depth — see the module docstring):

    1. :meth:`_purge_profile` deletes the user's ``profiles`` row on a **privileged, RLS-bypassing**
       session, cascading every domain row away. This is the load-bearing erasure on a DB that
       lacks the ``profiles → auth.users`` FK (the S1 bug).
    2. :meth:`_admin_delete_auth_user` removes the ``auth.users`` row via the service-role Admin API
       (revoking the user's sessions). On a DB that has the FK this also cascades — harmlessly
       re-deleting the already-gone profile.

    A custom ``transport`` is injectable so unit tests can drive the Admin call with an offline
    :class:`httpx.MockTransport` (no network).
    """

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def delete_user(self, user_id: uuid.UUID, *, db: AsyncSession) -> None:
        """Erase ``user_id`` entirely: domain data first, then the Supabase Auth identity.

        ``db`` must be a **privileged** session (``app.deps.get_usage_db`` → ``UsageSession``, which
        bypasses RLS) so the ``profiles`` delete and its cascade are not constrained by per-user
        policies. Fails closed (:class:`AccountAdminError`) *before touching anything* if the
        Supabase URL / service-role key are not configured — we never start a deletion we cannot
        finish. Both steps are idempotent (deleting an absent profile / an already-gone auth user is
        a no-op), and any failure raises :class:`AccountAdminError` so the caller reports an error
        (never a false success) and can safely retry.
        """
        base_url = (self._settings.supabase_url or "").rstrip("/")
        service_key = self._settings.supabase_service_role_key.get_secret_value()
        if not base_url or not service_key:
            # Fail closed up front: do not erase domain data if we cannot also erase the auth user.
            raise AccountAdminError("Supabase admin credentials are not configured")

        # 1. Erase domain data first, so a later auth-delete failure never leaves orphaned content.
        await self._purge_profile(user_id, db)
        # 2. Erase the auth identity (revokes refresh tokens; the FK cascade is a no-op here).
        await self._admin_delete_auth_user(user_id, base_url=base_url, service_key=service_key)

    async def _purge_profile(self, user_id: uuid.UUID, db: AsyncSession) -> None:
        """Hard-delete the user's ``profiles`` row (cascading all domain data) on ``db``.

        Idempotent: an absent profile deletes 0 rows. A DB failure is surfaced as
        :class:`AccountAdminError` (→ the router's ``502``) and the session is rolled back, so a
        broken erasure is never reported as success.
        """
        try:
            await db.execute(sql_delete(Profile).where(Profile.id == user_id))
            await db.commit()
        except SQLAlchemyError as exc:  # nothing reliably erased — surface as a retryable failure
            await db.rollback()
            raise AccountAdminError(f"profile hard-delete failed: {exc}") from exc

    async def _admin_delete_auth_user(
        self, user_id: uuid.UUID, *, base_url: str, service_key: str
    ) -> None:
        """DELETE ``user_id`` from ``auth.users`` via the service-role Admin API.

        Treats ``200``/``204`` (deleted) and ``404`` (already gone) as success; any other status or
        a network failure raises :class:`AccountAdminError`.
        """
        url = f"{base_url}/auth/v1/admin/users/{user_id}"
        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                # Send ``should_soft_delete=false`` EXPLICITLY rather than leaning on GoTrue's
                # implicit default: this is the most GDPR-load-bearing line in the auth step, so a
                # hard delete (which fires the ``auth.users → profiles → domain`` FK cascade where
                # the FK exists) must not be silently flippable to a soft delete by an upstream
                # default change. ``httpx.AsyncClient.delete`` takes no body, so use ``request``.
                response = await client.request(
                    "DELETE", url, headers=headers, json={"should_soft_delete": False}
                )
        except httpx.HTTPError as exc:  # network/timeout — auth user untouched, safe to retry
            raise AccountAdminError(f"auth admin request failed: {exc}") from exc

        if response.status_code not in _DELETE_OK:
            raise AccountAdminError(f"auth admin delete returned {response.status_code}")

    async def find_auth_user_id_by_email(self, email: str) -> uuid.UUID | None:
        """Resolve a Supabase Auth user id from an email via the service-role Admin API.

        Used by the **public** ``/delete-account`` request flow (task 8.3.1) to find which account a
        deletion link should be mailed to. Returns ``None`` — never raising — when the admin
        credentials are unset, when no user matches, or on any admin-API error, so the caller can
        always answer the same generic acknowledgement without disclosing whether the email exists
        (no account enumeration). Matching is case-insensitive on the normalized address.
        """
        base_url = (self._settings.supabase_url or "").rstrip("/")
        service_key = self._settings.supabase_service_role_key.get_secret_value()
        if not base_url or not service_key:
            return None

        target = email.strip().lower()
        url = f"{base_url}/auth/v1/admin/users"
        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                for page in range(1, _ADMIN_USERS_MAX_PAGES + 1):
                    response = await client.get(
                        url,
                        headers=headers,
                        params={"page": page, "per_page": _ADMIN_USERS_PER_PAGE},
                    )
                    if response.status_code != 200:
                        return None
                    users = response.json().get("users", [])
                    for user in users:
                        if str(user.get("email") or "").strip().lower() == target:
                            return uuid.UUID(str(user["id"]))
                    if len(users) < _ADMIN_USERS_PER_PAGE:
                        break  # last page reached; email not found
        except (httpx.HTTPError, ValueError, KeyError):
            # Network/parse/JSON failure — treat as "not found" so we never leak existence via an
            # error path (the endpoint's generic ack is returned regardless).
            return None
        return None
