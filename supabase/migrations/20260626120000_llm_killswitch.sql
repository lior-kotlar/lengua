-- LLM cost-guard kill-switch: server-only privilege model for llm_budget (Phase 3, group 3.1)
--
-- llm_budget is the GLOBAL daily cost-guard counter — the "I will never get a bill" backstop.
-- llm_usage is the per-user counter (its RLS owner policy scopes reads to the owner). Both must be
-- write-protected from the non-privileged `authenticated` role (and PostgREST): otherwise a
-- logged-in user could PATCH/DELETE their own llm_usage rows to reset their daily cap, or read/
-- tamper with the global llm_budget kill-switch for everyone. This migration locks both down:
--
--   1. A SECURITY DEFINER function `increment_llm_usage(uuid, text, date)` (owned by the migration
--      role) atomically bumps BOTH the per-user `llm_usage` row and the global `llm_budget` row in
--      one transaction (each via a row-locked `INSERT ... ON CONFLICT DO UPDATE`, so concurrent
--      callers can't lose an update) and returns the new global budget count. A SECURITY DEFINER
--      reader `get_llm_budget_count(date)` returns the day's budget (0 if none). Both schema-qualify
--      every table reference (`public.llm_usage` / `public.llm_budget`) — SECURITY DEFINER hardening,
--      since `pg_temp` is searched before the pinned `search_path = public` for relation names.
--   2. `llm_usage`: REVOKE INSERT/UPDATE/DELETE from `authenticated`/`anon` (SELECT kept, so the
--      RLS-scoped per-user count read still works); all writes go through (1), which runs as the
--      privileged owner.
--   3. `llm_budget`: REVOKE ALL from `authenticated`/`anon`, and ENABLE ROW LEVEL SECURITY with NO
--      policy (deny-by-default) as a second lock — so a stray future `GRANT ALL ... TO authenticated`
--      can't silently re-expose it. The `postgres` owner (the backend's privileged usage session)
--      and the SECURITY DEFINER functions both bypass RLS (no FORCE), so functionality is unchanged.
--   4. EXECUTE on BOTH functions is granted to `service_role` ONLY (the default PUBLIC grant is
--      revoked first). It is deliberately NOT granted to `authenticated`: Supabase exposes a
--      PostgREST RPC endpoint to that role, so `GRANT EXECUTE ... TO authenticated` would let any
--      logged-in user call `POST /rest/v1/rpc/increment_llm_usage` directly — bypassing the
--      backend's rate-limiter/caps and tripping the global kill-switch for everyone (a DoS on the
--      shared operator key). The backend instead invokes these via a privileged, server-only DB
--      session (the connecting `postgres`/owner role, which always retains EXECUTE).
--
-- Kept SEMANTICALLY in lockstep with Alembic migration 0004 — same objects/grants. (The Alembic
-- file guards every role GRANT/REVOKE with `to_regrole(...)` so it also round-trips on a bare
-- Postgres that lacks these Supabase roles; this canonical SQL runs them unconditionally because it
-- only ever runs on a real Supabase database.)

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

-- ── Read the day's global budget count (0 when no row yet) ──────────────────────────────────────
create or replace function public.get_llm_budget_count(p_day date)
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select count from public.llm_budget where day = p_day), 0);
$$;

-- ── Lock down the per-user counter: no client writes (SELECT kept for the RLS-scoped read) ──────
revoke insert, update, delete on table llm_usage from authenticated, anon;

-- ── Lock down the global kill-switch counter: server-only + deny-by-default RLS ────────────────
revoke all on table llm_budget from authenticated, anon;
alter table llm_budget enable row level security;  -- no policy → deny-all (owner/definer bypass)

-- ── Lock the functions to the server (service_role) only ───────────────────────────────────────
revoke all on function public.increment_llm_usage(uuid, text, date) from public, authenticated, anon;
revoke all on function public.get_llm_budget_count(date)            from public, authenticated, anon;

grant execute on function public.increment_llm_usage(uuid, text, date) to service_role;
grant execute on function public.get_llm_budget_count(date)            to service_role;
