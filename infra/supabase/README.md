# infra/supabase — Supabase setup notes

This directory holds the **owner-facing Supabase setup docs** that can't be committed as runnable
config (they depend on real secrets / dashboards). It does **not** hold the SQL.

- [`oauth-setup.md`](oauth-setup.md) — Google/Apple OAuth + custom SMTP (Resend) dashboard steps.
- This README — where the canonical Supabase SQL lives, how it relates to the Alembic schema, how to
  apply it per hosted project, and how to seed an environment.

## Where the canonical Supabase SQL lives — and why it stays there

The RLS policies, the `handle_new_user` trigger, and the LLM kill-switch privilege model are
**Supabase-specific** SQL (they reference `auth.users`, `auth.uid()`, and the `authenticated` /
`anon` / `service_role` roles). The canonical, CLI-native copy lives at the **repo root** under
[`supabase/migrations/`](../../supabase/migrations) — **not here** — because that is the directory
the Supabase CLI actually reads:

| File | What it owns |
|------|--------------|
| `supabase/migrations/20260621000000_initial_schema.sql` | Table reference DDL + **RLS policies** (owner-scoped `using/with check (… = auth.uid())` on every user table) + the **`handle_new_user` → `profiles` trigger**. |
| `supabase/migrations/20260626120000_llm_killswitch.sql` | The **server-only kill-switch**: `REVOKE`s `llm_usage`/`llm_budget` writes from `authenticated`/`anon`, deny-by-default RLS on `llm_budget`, and the `SECURITY DEFINER` increment/read functions granted to `service_role` only. |

> **Do not move these into `infra/supabase/`.** The local CLI stack (`supabase start`) and CI apply
> them from `supabase/migrations/` automatically; relocating them would break `supabase db …`. The
> plan text once said "move RLS into `infra/supabase/`" — that predates the CLI-native layout and is
> intentionally **not** done. This README is the documentation half of that decision (task 6.2.4).

## Relationship to the Alembic schema (source of truth for DDL)

Two tracks, kept **semantically in lockstep**:

- **Alembic** ([`apps/api/migrations/versions/`](../../apps/api/migrations/versions)) is the single
  source of truth for **table DDL** and is what applies the full schema to **staging / prod**. Its
  revisions mirror the Supabase-specific layer so a hosted Supabase DB ends up identical to the CLI
  stack:
  - `0001` — bare table DDL (no `auth` schema; runs on any Postgres).
  - `0002` — the `handle_new_user` profile-bootstrap trigger.
  - `0003` — the RLS policies.
  - `0004` — the kill-switch privilege model (mirrors `20260626120000_llm_killswitch.sql`).

  Revisions `0002`–`0004` apply on hosted Supabase because it has the `authenticated` role +
  `auth.uid()`. On a bare Alembic-only Postgres the role-dependent grants are guarded
  (`to_regrole(...)`) so they no-op rather than error.
- The **`supabase/migrations/*.sql`** files are the **canonical CLI-native form** of that same
  Supabase-specific layer — applied by the local stack and CI, and the reference the lockstep tests
  (`apps/api/tests/db/test_rls_migration.py`, `tests/db/test_role_privileges.py`) check the Alembic
  side against. Single source of truth for DDL = Alembic; CLI-native RLS/trigger/grant reference =
  `supabase/migrations/`.

## Applying to a hosted project (staging / prod)

The schema (incl. RLS/trigger/kill-switch) is applied to a hosted environment by pointing **Alembic**
at that env's connection string — see [`docs/runbook.md`](../../docs/runbook.md) → "Run a migration":

```bash
# From apps/api — the env is selected by the DB URL (there is no `-x env=` switch):
uv run alembic -x db_url="$SUPABASE_STAGING_DATABASE_URL" upgrade head
uv run alembic -x db_url="$SUPABASE_STAGING_DATABASE_URL" current   # == `alembic heads`
```

If you instead manage the RLS layer through the **Supabase CLI** track, link the project and push the
canonical migrations:

```bash
supabase link --project-ref <project-ref>   # staging rydclyotzdwcbbeyitcx · prod ptyqlxjykbprfzhnxgla
supabase db push                            # applies supabase/migrations/*.sql to the linked project
```

After either, `psql "$URL" -c '\dt'` lists the 8 app tables (+ `llm_usage` / `llm_budget`) and a
two-user RLS check proves isolation (`pytest apps/api/tests/test_rls.py` pointed at the env DB).

> **The live apply is owner-run.** Running this against the hosted staging/prod DBs needs the live
> connection strings + project refs and is tracked in
> [`planning/outstanding-work.md`](../../planning/outstanding-work.md) (tasks 6.2.2–6.2.4).

## Seeding per environment (task 6.2.5)

Both seed scripts are **idempotent** and select the environment from `DATABASE_URL` (plus
`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` for the auth-user creation path — they create the auth
user via the Supabase Auth Admin API, then the `handle_new_user` trigger makes the `profiles` row):

```bash
# From apps/api. Demo/reviewer account + a non-empty due deck (Spanish + a vowelized Hebrew RTL deck):
DATABASE_URL="$SUPABASE_STAGING_DATABASE_URL" \
SUPABASE_URL="<staging-supabase-url>" \
SUPABASE_SERVICE_ROLE_KEY="<staging-service-role-key>" \
  uv run python scripts/seed_e2e.py

# Or the single fixed dev-user profile:
DATABASE_URL="$SUPABASE_STAGING_DATABASE_URL" \
SUPABASE_URL="<staging-supabase-url>" \
SUPABASE_SERVICE_ROLE_KEY="<staging-service-role-key>" \
  uv run python scripts/seed_dev_user.py
```

Idempotency: the demo user is found-by-email (not recreated) and the language/card inserts use
`ON CONFLICT` / existence checks, so a **second run adds no duplicate rows** and the reviewer can log
in either way.

> **The live seed run is owner-run.** Running this against hosted staging (reviewer created on first
> run, no duplicate on the second, reviewer logs in) is tracked in
> [`planning/outstanding-work.md`](../../planning/outstanding-work.md) (task 6.2.5).
