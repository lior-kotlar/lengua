"""LLM cost-guard gates (Phase 3) — currently the per-user daily-cap gate (group 3.2).

Every LLM-spending request passes a *gate chain* before the provider is called. The documented
order (``planning/03-backend.md``) is::

    email-verified  →  rate-limit  →  daily-cap  →  global-budget

This module is the single chokepoint that chain lives in. **Group 3.2 implements only the
daily-cap gate**; the other three slot in around it without touching the call sites:

* email-verified (3.7) and rate-limit (3.3) run *before* the daily-cap check — add them at the top
  of :meth:`QuotaGuard.check`;
* the global-budget kill-switch (3.4) runs *after* the daily-cap check (read ``get_budget_count``
  on the privileged usage session already wired in here) — add it at the bottom of
  :meth:`QuotaGuard.check`.

The gate is applied two ways, both sharing this one :class:`QuotaGuard`:

* ``/generate``, ``/discover`` and ``/discover/accept`` use it as a **FastAPI dependency**
  (:func:`quota_guard`) — the cap is checked before the route body runs, and the route calls
  :meth:`QuotaGuard.record_success` after a successful provider call.
* ``/explain`` is cache-aware (Phase 1.5b: a hit on ``cards.word_explanations`` makes *no* provider
  call). A route dependency would gate+count even a free cache hit, so for explain the guard is
  built **unchecked** (``quota_guard("explain", enforce=False)``) and handed to ``ExplainService``,
  which calls :meth:`check`/:meth:`record_success` only on a cache **miss**. So a cache hit is free
  (no gate, no increment) and only a miss is gated and counted.

**Increment-on-success only.** A provider error (or a NotFound/validation error raised before the
provider call) must never bump a counter, so :meth:`record_success` is invoked by the call site
*after* the provider returns, never by :meth:`check`. The increment goes through
:class:`~app.repositories.usage.UsageRepository` on the **privileged** ``get_usage_db`` session and
commits that session's own transaction (independent of the request's app-data transaction). It
ALWAYS passes the JWT-derived ``user_id`` — never a client-supplied id — because the underlying
``SECURITY DEFINER`` function trusts its ``p_user_id`` argument. The increment bumps both
``llm_usage`` (the per-user, per-kind counter the cap reads) and the global ``llm_budget`` counter,
so the kill-switch's global tally starts accumulating now even though its *gate* lands in 3.4.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.db.session import UsageSession
from app.deps import get_current_user, get_db, get_usage_db
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings

#: The three LLM ``kind``s that consume the operator key and are metered by the cost guard.
Kind = str  # one of: "generate" | "discover" | "explain"

#: ``user_settings`` keys holding a user's per-kind daily-cap override (a stringified integer).
#: A missing / blank / non-numeric value falls back to the server default for that kind.
CAP_SETTING_KEYS: dict[Kind, str] = {
    "generate": "daily_cap_generate",
    "discover": "daily_cap_discover",
    "explain": "daily_cap_explain",
}

#: Server-side hard maxima per kind — the ceiling a user's own cap is clamped to.
_SERVER_MAX: dict[Kind, Callable[[Settings], int]] = {
    "generate": lambda s: s.max_generate_per_day,
    "discover": lambda s: s.max_discover_per_day,
    "explain": lambda s: s.max_explain_per_day,
}

#: Per-user defaults per kind, applied when ``user_settings`` carries no usable override.
_SERVER_DEFAULT: dict[Kind, Callable[[Settings], int]] = {
    "generate": lambda s: s.default_generate_per_day,
    "discover": lambda s: s.default_discover_per_day,
    "explain": lambda s: s.default_explain_per_day,
}


class DailyCapReached(Exception):
    """Raised by the daily-cap gate when a user has spent their per-kind ceiling for the day.

    Carries the offending ``kind`` so the registered exception handler can render the exact
    contract body ``{"code": "daily_cap_reached", "kind": kind}`` with HTTP 429. Modelled as a
    bare ``Exception`` (not a ``ServiceError``) so it surfaces identically whether raised from the
    route dependency (``/generate`` etc.) or from inside ``ExplainService`` (cache miss) — both are
    converted by the app-level handler, not a per-router ``try/except``.
    """

    def __init__(self, kind: Kind) -> None:
        self.kind = kind
        super().__init__(f"Daily cap reached for '{kind}'.")


def _utc_today() -> date:
    """Today's date in UTC — the day key both the cap read and the increment use."""
    return datetime.now(tz=UTC).date()


async def resolve_user_cap(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, kind: Kind
) -> int:
    """Resolve the effective daily cap for ``user_id``/``kind``.

    Reads the per-user override from ``user_settings`` (key :data:`CAP_SETTING_KEYS`) and clamps it
    to the hard server maximum with ``min()`` so a user can never raise their own cap past the
    operator limit. A missing, blank, or non-numeric setting falls back to the server **default**
    for that kind (which is itself ``<=`` the maximum).
    """
    raw = await SettingsRepository(db).get(user_id, CAP_SETTING_KEYS[kind])
    server_max = _SERVER_MAX[kind](settings)
    if raw is None or not raw.strip():
        return _SERVER_DEFAULT[kind](settings)
    try:
        user_cap = int(raw.strip())
    except ValueError:
        return _SERVER_DEFAULT[kind](settings)
    return min(user_cap, server_max)


async def enforce_daily_cap(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, kind: Kind
) -> None:
    """The daily-cap gate: raise :class:`DailyCapReached` when the user is at/over their cap.

    Compares today's ``get_user_daily_count`` (RLS-scoped read on the request session) to
    :func:`resolve_user_cap`; refuses with a 429 once ``count >= cap``. Read-only — it never
    increments (that is :meth:`QuotaGuard.record_success`, post-success).
    """
    cap = await resolve_user_cap(db, settings, user_id, kind)
    count = await UsageRepository(db).get_user_daily_count(user_id, kind, _utc_today())
    if count >= cap:
        raise DailyCapReached(kind)


class QuotaGuard:
    """The per-request cost-guard gate for one LLM ``kind``.

    Holds the request's identity + sessions so the call site can :meth:`check` the gate chain
    before spending the provider, and :meth:`record_success` the spend afterwards. Built by the
    :func:`quota_guard` dependency (which also :meth:`check`s it for the route-dependency
    endpoints); ``ExplainService`` builds it ``enforce=False`` and drives both methods itself.
    """

    def __init__(
        self,
        *,
        kind: Kind,
        user_id: uuid.UUID,
        db: AsyncSession,
        usage_db: UsageSession,
        settings: Settings,
    ) -> None:
        self._kind = kind
        self._user_id = user_id
        self._db = db
        self._usage_db = usage_db
        self._settings = settings

    async def check(self) -> None:
        """Run the gate chain; raise on the first failing gate.

        Today this is just the daily-cap gate (3.2). The documented order means future gates wrap
        it: email-verified (3.7) + rate-limit (3.3) go *above* this line, the global-budget
        kill-switch (3.4) goes *below* it.
        """
        await enforce_daily_cap(self._db, self._settings, self._user_id, self._kind)

    async def record_success(self) -> None:
        """Count one successful provider call: atomically bump ``llm_usage`` + ``llm_budget``.

        Called only after the provider returned successfully. Runs on the privileged
        ``get_usage_db`` session and commits that session's own transaction (independent of the
        request's app-data transaction). The id is always the JWT-derived ``user_id`` — never a
        client-supplied value — because the ``SECURITY DEFINER`` increment function trusts it.
        """
        await UsageRepository(self._usage_db).increment_usage(
            self._user_id, self._kind, _utc_today()
        )
        await self._usage_db.commit()


def quota_guard(kind: Kind, *, enforce: bool = True) -> Callable[..., Awaitable[QuotaGuard]]:
    """Build the FastAPI dependency that yields a :class:`QuotaGuard` for ``kind``.

    With ``enforce=True`` (the default, used by ``/generate``, ``/discover``,
    ``/discover/accept``) the dependency also runs :meth:`QuotaGuard.check` before the route body,
    so the cap is enforced up front and the route only needs to call ``record_success`` on success.
    With ``enforce=False`` it yields an unchecked guard for the cache-aware ``/explain`` path, where
    ``ExplainService`` decides when to gate.
    """

    async def _dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        usage_db: Annotated[UsageSession, Depends(get_usage_db)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> QuotaGuard:
        guard = QuotaGuard(kind=kind, user_id=user.id, db=db, usage_db=usage_db, settings=settings)
        if enforce:
            await guard.check()
        return guard

    return _dependency


async def _daily_cap_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`DailyCapReached` as the contract body with HTTP 429."""
    assert isinstance(exc, DailyCapReached)  # registered only for DailyCapReached
    return JSONResponse(
        status_code=429,
        content={"code": "daily_cap_reached", "kind": exc.kind},
    )


def register_quota_handlers(app: FastAPI) -> None:
    """Wire the cost-guard exception handlers onto ``app`` (called from ``create_app``)."""
    app.add_exception_handler(DailyCapReached, _daily_cap_handler)
