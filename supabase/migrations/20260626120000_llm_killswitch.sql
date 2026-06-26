-- LLM cost-guard kill-switch: server-only privilege model for llm_budget (Phase 3, group 3.1)
--
-- llm_budget is the GLOBAL daily cost-guard counter — the "I will never get a bill" backstop.
-- Unlike the per-user tables it has no RLS owner policy, so on its own the Supabase default
-- table grants would let any logged-in (`authenticated`) user SELECT/UPDATE it through PostgREST
-- and trip (or hide) the kill-switch for everyone. This migration locks that down:
--
--   1. A SECURITY DEFINER function `increment_llm_usage(uuid, text, date)` (owned by the migration
--      role) atomically bumps BOTH the per-user `llm_usage` row and the global `llm_budget` row in
--      one transaction (each via a row-locked `INSERT ... ON CONFLICT DO UPDATE`, so concurrent
--      callers can't lose an update) and returns the new global budget count.
--   2. A SECURITY DEFINER reader `get_llm_budget_count(date)` returns the day's budget (0 if none).
--   3. REVOKE ALL on `llm_budget` from `authenticated`/`anon` — the load-bearing control: the
--      authenticated role (hence PostgREST) can neither read nor tamper with the kill-switch.
--   4. EXECUTE on BOTH functions is granted to `service_role` ONLY (the default PUBLIC grant is
--      revoked first). It is deliberately NOT granted to `authenticated`: Supabase exposes a
--      PostgREST RPC endpoint to that role, so `GRANT EXECUTE ... TO authenticated` would let any
--      logged-in user call `POST /rest/v1/rpc/increment_llm_usage` directly — bypassing the
--      backend's rate-limiter/caps and tripping the global kill-switch for everyone (a DoS on the
--      shared operator key). The backend instead invokes these via a privileged, server-only DB
--      session (the connecting `postgres`/owner role, which always retains EXECUTE) — nothing about
--      `llm_budget` is reachable by `authenticated`/`anon`.
--
-- Kept byte-for-byte consistent with Alembic migration 0004 (the two schema sources must not drift).

-- ── Atomic both-counter increment (returns the new global budget count) ────────────────────────
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

-- ── Read the day's global budget count (0 when no row yet) ──────────────────────────────────────
create or replace function public.get_llm_budget_count(p_day date)
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select count from llm_budget where day = p_day), 0);
$$;

-- ── Lock llm_budget + the functions to the server (service_role) only ──────────────────────────
revoke all on table llm_budget from authenticated, anon;

revoke all on function public.increment_llm_usage(uuid, text, date) from public, authenticated, anon;
revoke all on function public.get_llm_budget_count(date)            from public, authenticated, anon;

grant execute on function public.increment_llm_usage(uuid, text, date) to service_role;
grant execute on function public.get_llm_budget_count(date)            to service_role;
