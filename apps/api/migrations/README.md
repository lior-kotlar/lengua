# Alembic migrations

Alembic owns the FastAPI backend's Postgres schema (task 1.4). The first migration
(`versions/…_initial_schema.py`) is the **entire app schema** — the 6 app tables
(`profiles`, `languages`, `cards`, `reviews`, `proficiency`, `user_settings`) plus the
two cost-guard tables (`llm_usage`, `llm_budget`) — matching the ORM models in
`app/db/models.py` and the canonical `supabase/migrations/20260621000000_initial_schema.sql`.

The migration is applyable on a **bare Postgres**: `profiles.id` is a plain `uuid` PK with no
`auth.users` foreign key, and there are no RLS policies. The `auth.users` FK, RLS, and the
`handle_new_user` trigger remain Supabase-migration / Phase-2 concerns (Supabase's own SQL owns
its `public` schema; Alembic is kept schema-equivalent for non-Supabase / canonical use).

## Usage

The DB URL is resolved at runtime from `DATABASE_URL` (via `app.settings`); `alembic.ini`
hard-codes nothing. Run from `apps/api`:

```bash
uv run alembic current              # show the applied revision (empty on a fresh DB)
uv run alembic upgrade head         # apply all migrations
uv run alembic downgrade base       # revert everything
uv run alembic revision --autogenerate -m "describe change"   # author a new migration
```

Target a one-off database without touching `DATABASE_URL`:

```bash
uv run alembic -x db_url=postgresql://postgres:postgres@127.0.0.1:54322/mytmp upgrade head
```

## Dev user

After `alembic upgrade head`, seed the fixed dev-user profile (the placeholder `current_user`
until Phase 2 auth):

```bash
uv run python scripts/seed_dev_user.py
```

It is idempotent and works on a bare Alembic-managed DB (direct `profiles` insert) and on
Supabase (creates the backing `auth.users` row with the same fixed id via the Auth Admin API).
