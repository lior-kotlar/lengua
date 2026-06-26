"""llm cost-guard kill-switch — server-only privilege model for llm_budget (task 3.1.2/3.1.3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-26

Reproduces, in Alembic, the kill-switch privilege model the canonical Supabase migration
(``supabase/migrations/20260626120000_llm_killswitch.sql``) defines, so a database built by
``alembic upgrade head`` matches one built by ``supabase db reset``. ``llm_budget`` is the GLOBAL
daily cost-guard counter (the "I will never get a bill" backstop): unlike the per-user tables it has
no RLS owner policy, so it must be made unreachable to the non-privileged ``authenticated`` role
(and therefore to Supabase's PostgREST) while still being writable by the server.

This migration adds:

1. ``public.increment_llm_usage(uuid, text, date)`` — a ``SECURITY DEFINER`` function (owned by the
   migration role, ``SET search_path = public``) that ATOMICALLY bumps both the per-user
   ``llm_usage`` row and the global ``llm_budget`` row (each via a row-locked
   ``INSERT ... ON CONFLICT DO UPDATE``, so concurrent callers cannot lose an update) and returns
   the new global budget count.
2. ``public.get_llm_budget_count(date)`` — a ``SECURITY DEFINER`` reader returning the day's budget
   count (0 when no row exists yet).
3. ``REVOKE ALL ON llm_budget FROM authenticated, anon`` — the load-bearing control so the
   authenticated role can neither SELECT nor UPDATE the kill-switch counter.
4. ``GRANT EXECUTE`` on both functions to ``service_role`` **only** (the default ``PUBLIC`` grant is
   revoked first, and ``authenticated``/``anon`` are revoked explicitly to defeat any Supabase
   default-privilege grant).

**Why EXECUTE is NOT granted to ``authenticated``.** Supabase exposes a PostgREST RPC endpoint to
the ``authenticated`` role, so granting it EXECUTE would let any logged-in user call
``POST /rest/v1/rpc/increment_llm_usage`` directly — bypassing the backend's rate-limiter/caps and
tripping the global kill-switch for everyone (a DoS on the shared operator key). The backend instead
invokes these through a privileged, server-only DB session (the connecting ``postgres``/owner role,
which always retains EXECUTE as the function owner) — see ``app.deps.get_usage_db``.

**Bare-Postgres safety.** The function bodies reference only the real ``llm_usage``/``llm_budget``
tables (created in 0001), so they are created on every database. The ``authenticated``/``anon``/
``service_role`` roles, however, exist only on a Supabase database (GoTrue/Supabase create them), so
every role GRANT/REVOKE is guarded by ``to_regrole(...) IS NOT NULL`` inside a ``DO`` block: on a
bare Postgres (the CI schema round-trip harness) those statements are a clean no-op, and the
migration still applies and round-trips. The ``REVOKE ... FROM PUBLIC`` runs unconditionally
(``PUBLIC`` always resolves) so the functions are never world-executable. The matching guard in
``downgrade`` restores the prior table privileges and drops the functions, keeping the round-trip
reversible on both kinds of database.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Matches supabase/migrations/20260626120000_llm_killswitch.sql verbatim (keep them in lockstep).
_CREATE_INCREMENT = """
create or replace function public.increment_llm_usage(
  p_user_id uuid,
  p_kind    text,
  p_day     date
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_budget integer;
begin
  insert into llm_usage (user_id, day, kind, count)
  values (p_user_id, p_day, p_kind, 1)
  on conflict (user_id, day, kind)
  do update set count = llm_usage.count + 1;

  insert into llm_budget (day, count)
  values (p_day, 1)
  on conflict (day)
  do update set count = llm_budget.count + 1
  returning count into v_budget;

  return v_budget;
end;
$$;
"""

_CREATE_READER = """
create or replace function public.get_llm_budget_count(p_day date)
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select count from llm_budget where day = p_day), 0);
$$;
"""

# Revoke the default PUBLIC EXECUTE unconditionally so the functions are never world-executable.
# (One statement per op.execute — asyncpg's extended-query protocol forbids multi-command strings.)
_REVOKE_PUBLIC_INCREMENT = (
    "revoke all on function public.increment_llm_usage(uuid, text, date) from public"
)
_REVOKE_PUBLIC_READER = "revoke all on function public.get_llm_budget_count(date) from public"

# Role grants/revokes only exist on a Supabase DB — guard each so a bare Postgres still round-trips.
_LOCK_DOWN_ROLES = """
do $$
begin
  if to_regrole('authenticated') is not null then
    revoke all on table llm_budget from authenticated;
    revoke all on function public.increment_llm_usage(uuid, text, date) from authenticated;
    revoke all on function public.get_llm_budget_count(date)            from authenticated;
  end if;
  if to_regrole('anon') is not null then
    revoke all on table llm_budget from anon;
    revoke all on function public.increment_llm_usage(uuid, text, date) from anon;
    revoke all on function public.get_llm_budget_count(date)            from anon;
  end if;
  if to_regrole('service_role') is not null then
    grant execute on function public.increment_llm_usage(uuid, text, date) to service_role;
    grant execute on function public.get_llm_budget_count(date)            to service_role;
  end if;
end
$$;
"""

# downgrade: restore the prior (Supabase-default) table privileges on llm_budget to authenticated/anon.
_RESTORE_ROLES = """
do $$
begin
  if to_regrole('authenticated') is not null then
    grant all on table llm_budget to authenticated;
  end if;
  if to_regrole('anon') is not null then
    grant all on table llm_budget to anon;
  end if;
end
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_INCREMENT)
    op.execute(_CREATE_READER)
    op.execute(_REVOKE_PUBLIC_INCREMENT)
    op.execute(_REVOKE_PUBLIC_READER)
    op.execute(_LOCK_DOWN_ROLES)


def downgrade() -> None:
    op.execute(_RESTORE_ROLES)
    op.execute("drop function if exists public.increment_llm_usage(uuid, text, date);")
    op.execute("drop function if exists public.get_llm_budget_count(date);")
