"""LLM cost-guard gates (Phase 3).

Every LLM-spending request passes a *gate chain* before the provider is called. The documented
order (``planning/03-backend.md``) is::

    email-verified  →  rate-limit  →  daily-cap  →  global-budget

This module is the single chokepoint that chain lives in, and :meth:`QuotaGuard.check` evaluates the
gates **in that order**, so the highest-priority (earliest) failure is the one that surfaces. The
gates landed across groups:

* **email-verified** (3.7.1) — only a verified account may spend the shared operator key; an
  unverified caller is refused with **403** ``{"code": "email_unverified"}`` before any limiter,
  counter, or provider is touched.
* **rate-limit** (3.3.2) — a per-user sliding window (:mod:`app.ratelimit`) counted across *all*
  gated kinds; over :data:`Settings.rate_limit_per_min` it refuses with **429**
  ``{"code": "rate_limited"}`` and a ``Retry-After`` header. The token is consumed the moment the
  request reaches this gate (i.e. after passing email), regardless of whether the daily-cap gate
  below then blocks — rate limiting is about *frequency*.
* **daily-cap** (3.2) — the per-user, per-kind daily ceiling; ``generate`` additionally gets the
  signup-abuse **day-0 clamp** (3.7.2: a brand-new account's effective generate cap is reduced for
  its first UTC day).
* **global-budget** kill-switch (3.4) — the project-wide "I will never get a bill" backstop and the
  LAST gate: it reads the GLOBAL ``llm_budget`` counter on the **privileged** usage session (the
  ``authenticated`` request role cannot read ``llm_budget``) and, once the day's count reaches
  :data:`Settings.global_daily_budget`, refuses *every* user with **429**
  ``{"code": "daily_limit_reached", "message": "Daily limit reached, please try again tomorrow."}``.
  Because the read precedes the provider call and the atomic increment lands only *after* success
  (:meth:`QuotaGuard.record_success`), concurrent in-flight requests can overshoot the ceiling
  slightly — bounded by ``LLM_MAX_CONCURRENCY`` (3.5) and acceptable because the budget sits far
  below the provider's free RPD. It is a deliberate *check-then-increment-on-success* design (not
  reserve-before-spend) so a failed provider call never burns budget (3.4.3); there is no
  refund/decrement path.

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
from app.ratelimit import RateLimiter, get_rate_limiter
from app.repositories.profiles import ProfilesRepository
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


class EmailUnverified(Exception):
    """Raised by the first gate (3.7.1) when the caller's email is not verified.

    Rendered as **403** ``{"code": "email_unverified"}`` by the registered handler. Like the other
    gate errors it is a bare ``Exception`` so it surfaces identically from the route dependency and
    from inside ``ExplainService`` (cache miss), both converted by the app-level handler.
    """


class RateLimited(Exception):
    """Raised by the rate-limit gate (3.3.2) when the per-user sliding window is full.

    Carries ``retry_after`` (whole seconds until a slot frees) so the handler can render **429**
    ``{"code": "rate_limited"}`` with a matching ``Retry-After`` header.
    """

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded.")


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


class GlobalBudgetReached(Exception):
    """Raised by the final gate (3.4) when the project-wide daily LLM budget is spent.

    The global kill-switch: rendered as **429** with the friendly contract body
    ``{"code": "daily_limit_reached", "message": <DAILY_LIMIT_MESSAGE>}`` for *every* caller once
    the day's ``llm_budget`` count reaches :data:`~app.settings.Settings.global_daily_budget`. Like
    the other gate errors it is a bare ``Exception`` so it surfaces identically from the route
    dependency and from inside ``ExplainService`` (cache miss), both converted by the app handler.
    """


#: The friendly, user-facing message returned when the global daily kill-switch has tripped. Kept as
#: a constant so the gate handler and tests reference the same exact string (it is part of the API
#: contract).
DAILY_LIMIT_MESSAGE = "Daily limit reached, please try again tomorrow."


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


async def _account_created_today(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """True when ``user_id``'s profile was created on the current UTC day (a day-0 account).

    Reads ``profiles.created_at`` via :class:`~app.repositories.profiles.ProfilesRepository` on the
    request (RLS-scoped) session — a user can always read their own profile. A missing profile is
    treated as *established* (return False) so the day-0 clamp never *over*-restricts on an
    unexpected absence; the gate above it (email-verified) already guarantees a real caller.
    """
    profile = await ProfilesRepository(db).get(user_id)
    if profile is None:
        return False
    return profile.created_at.astimezone(UTC).date() == _utc_today()


async def enforce_daily_cap(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, kind: Kind
) -> None:
    """The daily-cap gate: raise :class:`DailyCapReached` when the user is at/over their cap.

    Compares today's ``get_user_daily_count`` (RLS-scoped read on the request session) to the
    effective cap; refuses with a 429 once ``count >= cap``. Read-only — it never increments (that
    is :meth:`QuotaGuard.record_success`, post-success).

    **Signup-abuse day-0 clamp (3.7.2).** For ``generate`` the effective cap is
    ``min(resolve_user_cap(...), NEW_ACCOUNT_DAY0_GENERATE_CAP)`` while the account is on its first
    UTC day, so a brand-new account hits a reduced ceiling sooner and a burst of throwaway signups
    can't drain the shared key on day one. Established accounts use their normal resolved cap. The
    profile read is skipped when the resolved cap is already ``<=`` the day-0 ceiling (the clamp
    could not lower it). The clamp is generate-only for now; ``discover``/``explain`` could get
    their own day-0 ceilings later. (A CAPTCHA challenge on signup / first generate would slot in
    here as an additional day-0 gate — DESIGN-ONLY; not built.)
    """
    cap = await resolve_user_cap(db, settings, user_id, kind)
    if kind == "generate":
        day0_cap = settings.new_account_day0_generate_cap
        if cap > day0_cap and await _account_created_today(db, user_id):
            cap = day0_cap
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
        email_verified: bool,
        db: AsyncSession,
        usage_db: UsageSession,
        settings: Settings,
        rate_limiter: RateLimiter,
    ) -> None:
        self._kind = kind
        self._user_id = user_id
        self._email_verified = email_verified
        self._db = db
        self._usage_db = usage_db
        self._settings = settings
        self._rate_limiter = rate_limiter

    async def check(self) -> None:
        """Run the gate chain in documented order; raise on the first (highest-priority) failure.

        Order (``planning/03-backend.md``): **email-verified → rate-limit → daily-cap →
        global-budget**. The rate-limit token is consumed once the request passes the email gate,
        even if the daily-cap gate then blocks (rate limiting is about frequency, not success).
        """
        # 1) email-verified (3.7.1): the very first gate — no LLM spend for an unverified account.
        if not self._email_verified:
            raise EmailUnverified

        # 2) rate-limit (3.3.2): per-user sliding window across all gated kinds; consumes a token.
        decision = self._rate_limiter.hit(self._user_id)
        if not decision.allowed:
            raise RateLimited(decision.retry_after)

        # 3) daily-cap (3.2) + the generate-only day-0 signup-abuse clamp (3.7.2).
        await enforce_daily_cap(self._db, self._settings, self._user_id, self._kind)

        # 4) global-budget kill-switch (3.4): the LAST gate — the project-wide "I will never get a
        # bill" backstop. Read the GLOBAL counter on the PRIVILEGED usage session (the
        # ``authenticated`` request role is REVOKE'd from ``llm_budget`` and cannot EXECUTE the
        # reader, so this MUST run on ``self._usage_db``, never ``self._db``) and refuse EVERY
        # caller once the day's count reaches the ceiling. This is a deliberate
        # check-then-increment-on-success design: the read here precedes the provider call and the
        # atomic increment lands only AFTER success (``record_success``), so concurrent in-flight
        # requests can overshoot the ceiling slightly. That overshoot is bounded by
        # ``LLM_MAX_CONCURRENCY`` (3.5) and is acceptable because the budget sits far below the
        # provider's free RPD — we do NOT reserve before spending, because a failed/blocked provider
        # call must never burn budget (3.4.3), and there is no refund/decrement path.
        budget = await UsageRepository(self._usage_db).get_budget_count(_utc_today())
        if budget >= self._settings.global_daily_budget:
            raise GlobalBudgetReached

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
        rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    ) -> QuotaGuard:
        guard = QuotaGuard(
            kind=kind,
            user_id=user.id,
            email_verified=user.email_verified,
            db=db,
            usage_db=usage_db,
            settings=settings,
            rate_limiter=rate_limiter,
        )
        if enforce:
            await guard.check()
        return guard

    return _dependency


async def _email_unverified_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`EmailUnverified` as the contract body with HTTP 403."""
    assert isinstance(exc, EmailUnverified)  # registered only for EmailUnverified
    return JSONResponse(status_code=403, content={"code": "email_unverified"})


async def _rate_limited_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`RateLimited` as the contract body with HTTP 429 + a ``Retry-After`` header."""
    assert isinstance(exc, RateLimited)  # registered only for RateLimited
    return JSONResponse(
        status_code=429,
        content={"code": "rate_limited"},
        headers={"Retry-After": str(exc.retry_after)},
    )


async def _daily_cap_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`DailyCapReached` as the contract body with HTTP 429."""
    assert isinstance(exc, DailyCapReached)  # registered only for DailyCapReached
    return JSONResponse(
        status_code=429,
        content={"code": "daily_cap_reached", "kind": exc.kind},
    )


async def _global_budget_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`GlobalBudgetReached` as the friendly kill-switch body with HTTP 429.

    Status **429** (Too Many Requests) keeps the kill-switch consistent with the other quota gates
    (``rate_limited`` / ``daily_cap_reached``); ``planning/03-backend.md`` lists "503/429" for this
    gate without mandating 503, so we use 429 across the cost guard. The body is the exact contract
    shape ``{"code": "daily_limit_reached", "message": <friendly>}``.
    """
    assert isinstance(exc, GlobalBudgetReached)  # registered only for GlobalBudgetReached
    return JSONResponse(
        status_code=429,
        content={"code": "daily_limit_reached", "message": DAILY_LIMIT_MESSAGE},
    )


def register_quota_handlers(app: FastAPI) -> None:
    """Wire the cost-guard exception handlers onto ``app`` (called from ``create_app``)."""
    app.add_exception_handler(EmailUnverified, _email_unverified_handler)
    app.add_exception_handler(RateLimited, _rate_limited_handler)
    app.add_exception_handler(DailyCapReached, _daily_cap_handler)
    app.add_exception_handler(GlobalBudgetReached, _global_budget_handler)
