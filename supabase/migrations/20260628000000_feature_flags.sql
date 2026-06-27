-- Feature flags: global operator config table, locked down to the server (Phase 6, group 6.9)
--
-- public.feature_flags overlays the env-driven feature flags (app/feature_flags.py): a row
-- (name, enabled, updated_at) overrides the env default for that flag for EVERYONE, so a risky/new
-- feature can be toggled in prod WITHOUT a redeploy (the app picks the change up within
-- FEATURE_FLAG_TTL_SECONDS). Absence of a row ⇒ fall back to the env default (off).
--
-- SECURITY — this is GLOBAL config, NOT user data. Exactly like llm_budget (the global kill-switch
-- counter), feature_flags must be unwritable — and here unreadable — by the non-privileged
-- `authenticated`/`anon` roles, or a logged-in user could flip a flag on for everyone via PostgREST.
-- So:
--   1. REVOKE ALL ON feature_flags FROM authenticated, anon — no client SELECT/INSERT/UPDATE/DELETE.
--      Flag state reaches the browser ONLY through the public GET /feature-flags API endpoint (the
--      server resolves it on the privileged app connection), never by reading this table directly.
--      Writes are admin/service-role only.
--   2. ENABLE ROW LEVEL SECURITY with NO policy (deny-by-default) as a second lock, so a stray
--      future `GRANT ALL ... TO authenticated` can't silently re-expose it. The `postgres` owner
--      (the backend's app + migration role) and `service_role` both bypass RLS (no FORCE), so the
--      server read/write path is unchanged — mirrors llm_budget exactly.
--
-- Kept SEMANTICALLY in lockstep with Alembic migration 0005 — same table + grants. (The Alembic
-- file guards every role REVOKE with `to_regrole(...)` so it also round-trips on a bare Postgres
-- that lacks these Supabase roles; this canonical SQL runs them unconditionally because it only ever
-- runs on a real Supabase database.)

-- ── The global flag-override table ─────────────────────────────────────────────────────────────
create table if not exists public.feature_flags (
  name       text        primary key,
  enabled    boolean     not null default false,
  updated_at timestamptz not null default now()
);

-- ── Lock it down: server-only (no client reads/writes) + deny-by-default RLS ────────────────────
revoke all on table public.feature_flags from authenticated, anon;
alter table public.feature_flags enable row level security;  -- no policy → deny-all (owner bypasses)
