"""Persistence for the LLM cost-guard counters (task 3.1.3 / 3.1.4).

Two tables back the Phase 3 cost guard:

* ``llm_usage`` — a per-user, per-day, per-kind call counter (RLS owner policy: a user sees only
  their own rows), and
* ``llm_budget`` — the GLOBAL daily kill-switch counter. It is **server-only**: the migration
  ``REVOKE``\\s it from the ``authenticated``/``anon`` roles (and puts it under deny-by-default RLS)
  and exposes writes only through a ``SECURITY DEFINER`` function owned by the privileged role, so a
  logged-in user can neither read nor tamper with it.

This repository is the sole DB-touching layer for those counters (the Phase 1 boundary rule):

* :meth:`increment_usage` and :meth:`get_budget_count` go through the ``SECURITY DEFINER`` functions
  and therefore MUST run on a **privileged** session (``app.deps.get_usage_db``) — the connecting
  ``postgres``/owner role retains EXECUTE, whereas the per-request ``authenticated`` session does
  not. :meth:`increment_usage` performs the atomic both-counter bump in one statement, so concurrent
  callers cannot lose an update.
* :meth:`get_user_daily_count` is a plain ``SELECT`` on ``llm_usage`` and may run either on the
  normal RLS-bound request session (the owner policy scopes it to the caller) or on the privileged
  usage session (its explicit ``WHERE user_id`` scopes it); ``authenticated`` keeps SELECT on
  ``llm_usage`` for exactly this read while its writes are revoked.

Like the other repositories it takes an :class:`~sqlalchemy.ext.asyncio.AsyncSession` and does
**not** ``commit`` — the calling service owns the transaction boundary (for the privileged increment
that is the ``app.deps.get_usage_db`` session, which the service ``commit``\\s after a successful
provider call). The constructor takes a plain ``AsyncSession`` (not the ``UsageSession`` newtype)
precisely so :meth:`get_user_daily_count` can be served by the request session too; see ``§7`` of
``planning/outstanding-work.md`` for why a stronger compile-time session-type split is deferred.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LlmUsage


class UsageRepository:
    """Read and atomically bump the LLM cost-guard counters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def increment_usage(self, user_id: uuid.UUID, kind: str, day: date) -> int:
        """Atomically bump ``llm_usage`` and the global ``llm_budget`` for ``day``; return the new
        global budget count.

        Delegates to the ``SECURITY DEFINER`` ``public.increment_llm_usage`` function, which does
        both row-locked ``INSERT ... ON CONFLICT DO UPDATE`` bumps in a single statement so 50
        concurrent callers leave ``count == 50`` in both tables (no lost updates). **Must run on a
        privileged session** (``app.deps.get_usage_db``): the ``authenticated`` request role has no
        EXECUTE on the function.
        """
        result = await self._session.execute(
            text("SELECT public.increment_llm_usage(:uid, :kind, :day)"),
            {"uid": user_id, "kind": kind, "day": day},
        )
        return int(result.scalar_one())

    async def get_user_daily_count(self, user_id: uuid.UUID, kind: str, day: date) -> int:
        """Return the user's ``llm_usage`` count for ``(kind, day)`` — 0 when no row exists yet.

        A plain ``SELECT`` scoped by ``user_id``; safe on the RLS-bound request session (the
        ``llm_usage`` owner policy already limits it to the caller's rows).
        """
        stmt = select(LlmUsage.count).where(
            LlmUsage.user_id == user_id,
            LlmUsage.day == day,
            LlmUsage.kind == kind,
        )
        count = await self._session.scalar(stmt)
        return count if count is not None else 0

    async def get_budget_count(self, day: date) -> int:
        """Return the global ``llm_budget`` count for ``day`` — 0 when no row exists yet.

        Delegates to the ``SECURITY DEFINER`` reader ``public.get_llm_budget_count``, so it **must
        run on a privileged session** (``app.deps.get_usage_db``); the ``authenticated`` role can
        neither read ``llm_budget`` directly nor EXECUTE this function.
        """
        result = await self._session.execute(
            text("SELECT public.get_llm_budget_count(:day)"),
            {"day": day},
        )
        return int(result.scalar_one())
