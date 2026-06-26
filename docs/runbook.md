# Runbook

> **Placeholder.** This is a Phase 0 stub. The operational runbook is filled in
> as the deploy pipeline and observability land (Phases 5–6) and is finalized for
> launch (Phase 9). The sections below are intentionally empty for now.

## Health checks

_TODO: how to verify the service is healthy (e.g. `GET /health`), the dashboards
to watch, and what "healthy" looks like for the API, web app, and database._

## Deploy / rollback

_TODO: how to deploy to staging and production, how to promote a build, and the
exact steps to roll back a bad release._

> **Schema invariant — never migrate prod with Alembic-only.** `DELETE /account` relies on the
> `auth.users → profiles` `ON DELETE CASCADE` present in the canonical Supabase schema
> (`supabase/migrations/...`), which the bare Alembic-0001 schema intentionally omits (it has no
> `auth` schema to reference); prod is Supabase so the cascade holds, but prod must **never** be
> migrated via Alembic-only or a deletion would orphan the profile and all domain data.

## On-call

_TODO: on-call rotation, escalation path, alert routing, and the first-response
checklist for an incident._

## Historical data import (legacy SQLite → Postgres)

One-off migration of the operator's pre-productionization learning history from the legacy
single-user SQLite database (`apps/api/data/lengua.db`) into the new multi-tenant Postgres
schema, under the operator's real account. Run by `apps/api/scripts/import_sqlite.py` (task 2.7).

**Prerequisites**

- The target account already exists in Supabase Auth (the operator has signed up), so its
  `profiles` row exists. Get the account UUID from the Supabase dashboard (Authentication →
  Users) or `select id from auth.users where email = '<operator email>'`.
- A **privileged** `DATABASE_URL` (the `postgres` superuser DSN, e.g. from the Supabase project's
  connection settings). RLS makes the request-path role (`authenticated`) unable to write another
  user's rows, so the import **must** use the privileged connection — never the app's request path.
- A copy of the legacy `data/lengua.db` reachable from where you run the script.

**Procedure** (run from `apps/api`):

```bash
# 1. Dry run first — reports the planned inserts per table, writes NOTHING.
uv run python scripts/import_sqlite.py \
    --user-id <OPERATOR_UUID> \
    --sqlite-path data/lengua.db \
    --database-url "$DATABASE_URL" \
    --dry-run

# 2. Real import once the dry-run counts look right.
uv run python scripts/import_sqlite.py \
    --user-id <OPERATOR_UUID> \
    --sqlite-path data/lengua.db \
    --database-url "$DATABASE_URL"
```

`--sqlite-path` defaults to `data/lengua.db` and `--database-url` to `$DATABASE_URL`, so both can
be omitted when running with those defaults.

**What it does:** maps the old integer/global schema to the new schema, stamping every
`languages` / `cards` / `reviews` / `proficiency` row (and the legacy `settings` → `user_settings`)
with the target `user_id`, preserving `fsrs_state`, `due`, `saved`, and the proficiency scores.
Old integer ids are remapped to the new identity ids (parent → child), so the import never
collides with rows the account already created in the app.

**Idempotency / re-running:** the import is guarded by a natural key per table (languages on
`(user_id, name)`, cards on `(user_id, language_id, front, back, direction)`, reviews on
`(user_id, card_id, rating, reviewed_at)`, and the composite-PK `proficiency` / `user_settings`),
so re-running inserts nothing new — the row counts stay the same. The whole import runs in a single
transaction (all-or-nothing); `--dry-run` rolls that transaction back.

**Verify after import:** the per-table `inserted` counts in the report match the source row counts,
and a spot check of the operator's deck (`GET /review/due` after logging in, or a direct
`select count(*) from cards where user_id = '<OPERATOR_UUID>'`) shows the expected cards.
