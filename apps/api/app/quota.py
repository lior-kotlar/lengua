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
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import Span
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.db.session import UsageSession
from app.deps import get_current_user, get_db, get_usage_db
from app.llm_observability import (
    ATTR_BUDGET_REMAINING,
    ATTR_LLM_TOKENS_IN,
    ATTR_LLM_TOKENS_OUT,
    ATTR_QUOTA_CAP_HIT,
    CAP_HIT_NONE,
    RESULT_BLOCKED,
    RESULT_ERROR,
    RESULT_SUCCESS,
    peek_budget_remaining,
    record_call,
    record_cap_hit,
    set_budget_remaining,
    start_llm_span,
)
from app.ratelimit import RateLimiter, get_rate_limiter
from app.repositories.profiles import ProfilesRepository
from app.repositories.settings import SettingsRepository
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings

# ``quota.cap_hit`` values / ``llm_cap_hits_total{gate}`` labels — one per gate, matching the
# documented chain order. The span/metric blocked-reason strings live as constants so the gate logic
# and the observability tests reference the same vocabulary.
GATE_EMAIL = "email"
GATE_RATE = "rate"
GATE_DAILY_CAP = "daily_cap"
GATE_GLOBAL_BUDGET = "global_budget"

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


async def _account_created_today(db: AsyncSession, user_id: uuid.UUID, day: date) -> bool:
    """True when ``user_id``'s profile was created on ``day`` (UTC) — a day-0 account.

    Reads ``profiles.created_at`` via :class:`~app.repositories.profiles.ProfilesRepository` on the
    request (RLS-scoped) session — a user can always read their own profile. A missing profile is
    treated as *established* (return False) so the day-0 clamp never *over*-restricts on an
    unexpected absence; the gate above it (email-verified) already guarantees a real caller. ``day``
    is the request's single UTC day (computed once in :meth:`QuotaGuard.check`) so every read and
    the later increment agree even across a 00:00-UTC boundary.
    """
    profile = await ProfilesRepository(db).get(user_id)
    if profile is None:
        return False
    return profile.created_at.astimezone(UTC).date() == day


async def enforce_daily_cap(
    db: AsyncSession, settings: Settings, user_id: uuid.UUID, kind: Kind, day: date | None = None
) -> None:
    """The daily-cap gate: raise :class:`DailyCapReached` when the user is at/over their cap.

    Compares ``day``'s ``get_user_daily_count`` (RLS-scoped read on the request session) to the
    effective cap; refuses with a 429 once ``count >= cap``. Read-only — it never increments (that
    is :meth:`QuotaGuard.record_success`, post-success). ``day`` defaults to the current UTC day;
    the gate chain (:meth:`QuotaGuard.check`) passes the request's single, already-computed UTC day
    so the cap read, the budget read, and the later increment all reference the same day.

    **Signup-abuse day-0 clamp (3.7.2).** For ``generate`` the effective cap is
    ``min(resolve_user_cap(...), NEW_ACCOUNT_DAY0_GENERATE_CAP)`` while the account is on its first
    UTC day, so a brand-new account hits a reduced ceiling sooner and a burst of throwaway signups
    can't drain the shared key on day one. Established accounts use their normal resolved cap. The
    profile read is skipped when the resolved cap is already ``<=`` the day-0 ceiling (the clamp
    could not lower it). The clamp is generate-only for now; ``discover``/``explain`` could get
    their own day-0 ceilings later. (A CAPTCHA challenge on signup / first generate would slot in
    here as an additional day-0 gate — DESIGN-ONLY; not built.)
    """
    if day is None:
        day = _utc_today()
    cap = await resolve_user_cap(db, settings, user_id, kind)
    if kind == "generate":
        day0_cap = settings.new_account_day0_generate_cap
        if cap > day0_cap and await _account_created_today(db, user_id, day):
            cap = day0_cap
    count = await UsageRepository(db).get_user_daily_count(user_id, kind, day)
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
        # The request's single UTC day, fixed by :meth:`check` and reused by :meth:`record_success`
        # so a request straddling 00:00 UTC reads and increments the SAME day's counters (never
        # reads day N then increments day N+1). ``None`` until ``check`` runs; ``record_success``
        # falls back to "now" only if it was somehow called without ``check`` (never on real paths).
        self._day: date | None = None
        # The per-call ``llm.call`` observability span (task 3.8.1), started by :meth:`check` and
        # ended exactly once by :meth:`record_success` / :meth:`_block` / :meth:`finalize`. ``None``
        # until ``check`` runs (so a free cache hit, which never calls ``check``, emits no span).
        self._span: Span | None = None
        self._finalized = False

    @property
    def span(self) -> Span | None:
        """The per-call ``llm.call`` span (or ``None`` before :meth:`check`), for the call boundary.

        :func:`app.llm_runner.run_provider` reads this to stamp the ``llm.*`` attributes
        (provider/model/latency/tokens) on the same span the gate carries ``quota.*`` on.
        """
        return self._span

    async def check(self) -> None:
        """Run the gate chain in documented order; raise on the first (highest-priority) failure.

        Order (``planning/03-backend.md``): **email-verified → rate-limit → daily-cap →
        global-budget**. The rate-limit token is consumed once the request passes the email gate,
        even if the daily-cap gate then blocks (rate limiting is about frequency, not success).

        Starts the per-call ``llm.call`` span (task 3.8.1) and stamps ``quota.kind``. On a block it
        sets ``quota.cap_hit`` to the blocking gate, records the blocked metrics, ends the span,
        and raises; on admission it sets ``quota.cap_hit=none`` and leaves the span open for the
        provider call + :meth:`record_success` to finish.
        """
        # Pin the request's UTC day ONCE here, then thread the same value through the daily-cap
        # read, the budget read, and the increment so they never disagree across a midnight flip.
        day = _utc_today()
        self._day = day
        span = start_llm_span(self._kind)
        self._span = span

        # 1) email-verified (3.7.1): the very first gate — no LLM spend for an unverified account.
        if not self._email_verified:
            self._block(GATE_EMAIL)
            raise EmailUnverified

        # 2) rate-limit (3.3.2): per-user sliding window across all gated kinds; consumes a token.
        decision = self._rate_limiter.hit(self._user_id)
        if not decision.allowed:
            self._block(GATE_RATE)
            raise RateLimited(decision.retry_after)

        # 3) daily-cap (3.2) + the generate-only day-0 signup-abuse clamp (3.7.2).
        try:
            await enforce_daily_cap(self._db, self._settings, self._user_id, self._kind, day)
        except DailyCapReached:
            self._block(GATE_DAILY_CAP)
            raise

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
        budget_count = await UsageRepository(self._usage_db).get_budget_count(day)
        remaining = self._settings.global_daily_budget - budget_count
        set_budget_remaining(remaining)  # refresh the observable gauge from the just-read count
        span.set_attribute(ATTR_BUDGET_REMAINING, remaining)
        if budget_count >= self._settings.global_daily_budget:
            self._block(GATE_GLOBAL_BUDGET, budget_remaining=remaining)
            raise GlobalBudgetReached

        # Admitted: record the cap-hit attribute now; ``llm.*`` + the final budget land later.
        span.set_attribute(ATTR_QUOTA_CAP_HIT, CAP_HIT_NONE)

    def _block(self, gate: str, *, budget_remaining: int | None = None) -> None:
        """Finalize the span for a call refused by ``gate``: cap-hit + tokens 0 + blocked metrics.

        A blocked call never reaches the provider, so it records ``llm.tokens_in/out = 0`` and still
        emits a complete span. ``budget_remaining`` is the freshly-read value for a global-budget
        block; for an earlier gate (email / rate / daily-cap, which never read the budget) it falls
        back to the last-known remaining so the span still carries ``budget.remaining`` without an
        extra privileged DB read on the fast-fail path.
        """
        assert self._span is not None  # _block only runs from check(), which started the span
        if budget_remaining is None:
            budget_remaining = peek_budget_remaining(self._settings.global_daily_budget)
        self._span.set_attribute(ATTR_QUOTA_CAP_HIT, gate)
        self._span.set_attribute(ATTR_LLM_TOKENS_IN, 0)
        self._span.set_attribute(ATTR_LLM_TOKENS_OUT, 0)
        self._span.set_attribute(ATTR_BUDGET_REMAINING, budget_remaining)
        record_cap_hit(gate)
        record_call(self._kind, RESULT_BLOCKED)
        self._span.end()
        self._finalized = True

    async def record_success(self) -> None:
        """Count one successful provider call: atomically bump ``llm_usage`` + ``llm_budget``.

        Called only after the provider returned successfully, and always after :meth:`check` (every
        call site runs the chain first), so it reuses the same UTC ``day`` :meth:`check` pinned —
        read and increment never straddle a day boundary. Runs on the privileged ``get_usage_db``
        session and commits that session's own transaction (independent of the request's app-data
        transaction). The id is always the JWT-derived ``user_id`` — never a client-supplied value —
        because the ``SECURITY DEFINER`` increment function trusts it.

        Also finishes the per-call span (task 3.8.1): refreshes ``budget.remaining`` from the new
        count, records the ``success`` metric + the budget gauge, and ends the span.
        """
        day = self._day if self._day is not None else _utc_today()
        new_count = await UsageRepository(self._usage_db).increment_usage(
            self._user_id, self._kind, day
        )
        await self._usage_db.commit()
        remaining = self._settings.global_daily_budget - new_count
        set_budget_remaining(remaining)
        record_call(self._kind, RESULT_SUCCESS)
        assert self._span is not None  # record_success always follows check()
        self._span.set_attribute(ATTR_BUDGET_REMAINING, remaining)
        self._span.end()
        self._finalized = True

    def finalize(self) -> None:
        """End the span as an ``error`` if it was admitted but neither recorded nor blocked.

        Called from the :func:`quota_guard` dependency's teardown (always, on every path). It is a
        no-op when there is no span (a free cache hit never called :meth:`check`) or the span was
        already ended (:meth:`record_success` on success, :meth:`_block` on a gate block). The only
        remaining case — ``check`` passed but the provider call (or a later step) raised before
        ``record_success`` — is recorded as a failed ``error`` call so a provider error still emits
        a complete span + metric.
        """
        if self._span is not None and not self._finalized:
            record_call(self._kind, RESULT_ERROR)
            self._span.end()
            self._finalized = True


def quota_guard(kind: Kind, *, enforce: bool = True) -> Callable[..., AsyncIterator[QuotaGuard]]:
    """Build the FastAPI dependency that yields a :class:`QuotaGuard` for ``kind``.

    With ``enforce=True`` (the default, used by ``/generate``, ``/discover``,
    ``/discover/accept``) the dependency also runs :meth:`QuotaGuard.check` before the route body,
    so the cap is enforced up front and the route only needs to call ``record_success`` on success.
    With ``enforce=False`` it yields an unchecked guard for the cache-aware ``/explain`` /
    ``/discover`` paths, where the service decides when to gate.

    It is a **generator** dependency so the per-call observability span (task 3.8.1) is always
    finalized via :meth:`QuotaGuard.finalize` in teardown — even when the route body raises (a
    provider error) after the gate admitted the call.
    """

    async def _dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        usage_db: Annotated[UsageSession, Depends(get_usage_db)],
        settings: Annotated[Settings, Depends(get_settings)],
        rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    ) -> AsyncIterator[QuotaGuard]:
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
            # A block here ends the span itself (``_block``) and raises before the yield, so the
            # ``finally`` is never reached for a blocked enforced call.
            await guard.check()
        try:
            yield guard
        finally:
            guard.finalize()

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
