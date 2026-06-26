"""llm cost-guard kill-switch — server-only privilege model for the usage counters (task 3.1.2/3.1.3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-26

Reproduces, in Alembic, the kill-switch privilege model the canonical Supabase migration
(``supabase/migrations/20260626120000_llm_killswitch.sql``) defines, so a database built by
``alembic upgrade head`` matches one built by ``supabase db reset``. ``llm_usage`` is the per-user
call counter (its RLS owner policy scopes reads to the owner); ``llm_budget`` is the GLOBAL daily
cost-guard counter (the "I will never get a bill" backstop). Both must be unwritable by the
non-privileged ``authenticated`` role (and therefore by Supabase's PostgREST) while staying writable
by the server, or a logged-in user could reset their own daily cap (``llm_usage``) or trip/hide the
global kill-switch for everyone (``llm_budget``).

This migration adds:

1. ``public.increment_llm_usage(uuid, text, date)`` — a ``SECURITY DEFINER`` function (owned by the
   migration role, ``SET search_path = public``) that ATOMICALLY bumps both the per-user
   ``llm_usage`` row and the global ``llm_budget`` row (each via a row-locked
   ``INSERT ... ON CONFLICT DO UPDATE``, so concurrent callers cannot lose an update) and returns
   the new global budget count.
2. ``public.get_llm_budget_count(date)`` — a ``SECURITY DEFINER`` reader returning the day's budget
   count (0 when no row exists yet). Both functions schema-qualify every table reference
   (``public.llm_usage`` / ``public.llm_budget``): ``pg_temp`` is searched before the pinned
   ``search_path = public`` for relation names, so qualifying them is standard SECURITY DEFINER
   hardening against a search-path shadowing attack.
3. ``REVOKE INSERT/UPDATE/DELETE ON llm_usage FROM authenticated, anon`` (SELECT kept, so the
   RLS-scoped per-user count read still works) — all writes go through (1).
4. ``REVOKE ALL ON llm_budget FROM authenticated, anon`` **and** ``ENABLE ROW LEVEL SECURITY`` on it
   with NO policy (deny-by-default), a second lock so a stray future ``GRANT ALL ... TO
   authenticated`` can't silently re-expose the kill-switch. The owner/definer bypass RLS (no
   ``FORCE``), so the server path is unchanged.
5. ``GRANT EXECUTE`` on both functions to ``service_role`` **only** (the default ``PUBLIC`` grant is
   revoked first, and ``authenticated``/``anon`` are revoked explicitly to defeat any Supabase
   default-privilege grant).

**Why EXECUTE is NOT granted to ``authenticated``.** Supabase exposes a PostgREST RPC endpoint to
the ``authenticated`` role, so granting it EXECUTE would let any logged-in user call
``POST /rest/v1/rpc/increment_llm_usage`` directly — bypassing the backend's rate-limiter/caps and
tripping the global kill-switch for everyone (a DoS on the shared operator key). The backend instead
invokes these through a privileged, server-only DB session (the connecting ``postgres``/owner role,
which always retains EXECUTE as the function owner) — see ``app.deps.get_usage_db``.

**Bare-Postgres safety.** The function bodies and the ``ENABLE ROW LEVEL SECURITY`` reference only
the real ``llm_usage``/``llm_budget`` tables (created in 0001), so they apply on every database. The
``authenticated``/``anon``/``service_role`` roles, however, exist only on a Supabase database
(GoTrue/Supabase create them), so every role GRANT/REVOKE is guarded by ``to_regrole(...) IS NOT
NULL`` inside a ``DO`` block: on a bare Postgres (the CI schema round-trip harness) those statements
are a clean no-op, and the migration still applies and round-trips. The ``REVOKE ... FROM PUBLIC``
runs unconditionally (``PUBLIC`` always resolves) so the functions are never world-executable. The
matching guard in ``downgrade`` restores the prior table privileges, disables the ``llm_budget`` RLS,
and drops the functions, keeping the round-trip reversible on both kinds of database.

This migration is kept SEMANTICALLY in lockstep with the canonical Supabase SQL — same objects and
grants; only the role-statement guarding differs (Alembic guards via ``to_regrole``; the Supabase SQL
runs unconditionally, as it only ever runs on a real Supabase DB).

⚠️ **Production caveat:** do NOT ``alembic downgrade`` past 0004 in production — the downgrade
re-grants ``authenticated``/``anon`` access to ``llm_budget`` and drops the increment/read functions,
re-exposing the global kill-switch. (Carry this into the Phase 6 deploy runbook; see docs/runbook.md.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Semantically matches supabase/migrations/20260626120000_llm_killswitch.sql (keep them in lockstep).
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
  insert into public.llm_usage (user_id, day, kind, count)
  values (p_user_id, p_day, p_kind, 1)
  on conflict (user_id, day, kind)
  do update set count = public.llm_usage.count + 1;

  insert into public.llm_budget (day, count)
  values (p_day, 1)
  on conflict (day)
  do update set count = public.llm_budget.count + 1
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
  select coalesce((select count from public.llm_budget where day = p_day), 0);
$$;
"""

# Deny-by-default RLS on the global kill-switch (no policy). Unconditional — works on bare Postgres
# (no role needed); the owner/definer bypass RLS so the server path is unaffected.
_ENABLE_BUDGET_RLS = "alter table llm_budget enable row level security"
_DISABLE_BUDGET_RLS = "alter table llm_budget disable row level security"

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
    revoke insert, update, delete on table llm_usage from authenticated;
    revoke all on table llm_budget from authenticated;
    revoke all on function public.increment_llm_usage(uuid, text, date) from authenticated;
    revoke all on function public.get_llm_budget_count(date)            from authenticated;
  end if;
  if to_regrole('anon') is not null then
    revoke insert, update, delete on table llm_usage from anon;
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

# downgrade: restore the prior (Supabase-default) table privileges to authenticated/anon.
_RESTORE_ROLES = """
do $$
begin
  if to_regrole('authenticated') is not null then
    grant insert, update, delete on table llm_usage to authenticated;
    grant all on table llm_budget to authenticated;
  end if;
  if to_regrole('anon') is not null then
    grant insert, update, delete on table llm_usage to anon;
    grant all on table llm_budget to anon;
  end if;
end
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_INCREMENT)
    op.execute(_CREATE_READER)
    op.execute(_ENABLE_BUDGET_RLS)
    op.execute(_REVOKE_PUBLIC_INCREMENT)
    op.execute(_REVOKE_PUBLIC_READER)
    op.execute(_LOCK_DOWN_ROLES)


def downgrade() -> None:
    op.execute(_RESTORE_ROLES)
    op.execute(_DISABLE_BUDGET_RLS)
    op.execute("drop function if exists public.increment_llm_usage(uuid, text, date);")
    op.execute("drop function if exists public.get_llm_budget_count(date);")
