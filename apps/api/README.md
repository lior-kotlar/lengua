# apps/api — Lengua API (FastAPI)

The FastAPI backend service, managed with [`uv`](https://docs.astral.sh/uv/) on Python 3.12.

## Structure

- `app/` — HTTP layer: `main.py` (FastAPI app + `GET /health`), `settings.py`
  (pydantic-settings config), `db/` (async SQLAlchemy 2.0 engine/session via `get_db` plus the
  typed ORM models in `db/models.py`, matching the canonical Supabase schema). Routers, auth,
  quota, and OTel wiring land in Phase 1.
- `lengua_core/` — domain logic (LLM provider seam, scheduler, proficiency, prompts, models);
  ported here in task 0.1.2 (renamed from the old root `lengua/` package).
- `legacy_streamlit/` — the legacy Streamlit app (`app.py` + `pages/`), relocated here in task
  0.1.2; run with `cd apps/api && streamlit run legacy_streamlit/app.py`.
- `lengua_core/llm/` — the provider-agnostic LLM seam: a `LLMProvider` Protocol (`base.py`),
  `get_provider()` selecting the impl from `LLM_PROVIDER` and failing fast on a missing key
  (`provider.py`), and the implementations behind it — `groq.py` (default; Groq's
  OpenAI-compatible JSON mode), `gemini.py` (reserved for prod; `google-genai` schema output),
  the deterministic offline `FakeLLM` (`fake.py`), and a shared retry/backoff + request-cap
  helper (`retry.py`). Switching providers is a config flip of `LLM_PROVIDER`, never a code
  change.
- `scripts/` — dev/ops scripts: `verify.py` (the local gate), `seed_e2e.py` (E2E demo-account
  seeder), `seed_dev_user.py` (the fixed dev-user profile used as the placeholder
  `current_user` until Phase 2), and `import_sqlite.py` (one-off import of the operator's legacy
  `data/lengua.db` history into Postgres under one account — see "Importing legacy data" below).
- `tests/` — pytest suite. Unit tests (`test_health.py`, `test_settings.py`, `test_factories.py`,
  `test_fake_llm.py`) plus DB-backed integration tests (`test_db_fixture.py`, `test_seed.py`, and
  the migration tests under `tests/db/` — `test_schema_roundtrip.py`, `test_seed_dev_user.py`).
  Shared fixtures + the Supabase-CLI Postgres wiring live in `conftest.py`; deterministic builders
  in `factories.py`.
- `migrations/` — Alembic: `env.py` (async, targets `app.db.Base.metadata`, URL from
  `DATABASE_URL`) + the first migration (the full schema). See [migrations/README.md](migrations/README.md).
- `Dockerfile`, `pyproject.toml`.

> `lengua_core/` and `legacy_streamlit/` are pre-existing and intentionally **out of scope**
> for the API's ruff/mypy gate — the configs in `pyproject.toml` target `app/` + `tests/` only.

## Run

Install deps and start the API (serves `GET /health` → `{"status":"ok"}`):

```
cd apps/api
uv sync
uv run uvicorn app.main:app          # http://127.0.0.1:8000/health
```

## Verify (lint + format + types + tests)

Runs ruff (lint + format check), mypy, and pytest with branch coverage (fails under 80%):

```
cd apps/api
uv run python scripts/verify.py
```

Or run the steps individually:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest --cov --cov-branch
```

## Test infrastructure

The suite splits into **unit** tests (no I/O — run anywhere, offline) and **integration** tests
marked `@pytest.mark.integration` that need a Postgres. Integration tests **auto-skip** when the
database is unreachable, so plain `uv run pytest` stays green with nothing running.

To run the integration tests (and the E2E seed), start the local Supabase stack from the repo
root first — it brings up Postgres on `54322` + Auth on `54321` and applies the migration:

```
supabase start                      # from the repo root
cd apps/api
uv run pytest                       # unit + integration (integration auto-skips if no DB)
```

The fixtures auto-source `DATABASE_URL` / `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` from
`supabase status` when unset, so no manual env export is needed for a local stack. Isolation:
each test module starts from a `TRUNCATE … RESTART IDENTITY CASCADE` of the app tables, and each
test runs inside a transaction rolled back at teardown — the sync `db` (psycopg) fixture and the
async `db_session` (SQLAlchemy `AsyncSession`, via `pytest-asyncio`) fixture both follow this
rollback-per-test pattern.

The LLM is never called in tests: `FakeLLM` (`LLM_PROVIDER=fake`) is a deterministic, network-free
stand-in (`tests/test_fake_llm.py` runs with `pytest-socket --disable-socket` to prove it).

Seed the deterministic demo/reviewer account (idempotent — creates the auth user via the Supabase
Auth Admin API, then a language + a set of due cards) for E2E:

```
uv run python scripts/seed_e2e.py
```

## Migrations (Alembic)

Alembic owns the schema. The database URL is resolved at runtime from `DATABASE_URL` (via
`app.settings`), so nothing is hard-coded in `alembic.ini`. Run from `apps/api`:

```
uv run alembic current              # applied revision (empty on a fresh DB)
uv run alembic upgrade head         # apply all migrations
uv run alembic downgrade base       # revert everything
uv run alembic check                # fail if the migrations drift from the ORM models
```

The first migration is the entire schema (the 6 app tables + the `llm_usage` / `llm_budget`
cost-guard tables), kept equivalent to `supabase/migrations/…_initial_schema.sql` and applyable
on a bare Postgres (no `auth.users` FK, no RLS — those stay Supabase / Phase-2 concerns). After
`upgrade head`, seed the fixed dev-user profile (idempotent):

```
uv run python scripts/seed_dev_user.py
```

## Importing legacy data

`scripts/import_sqlite.py` is a one-off admin migration of the operator's pre-productionization
history from the legacy single-user SQLite DB (`data/lengua.db`) into the multi-tenant Postgres
schema, under one target account UUID. It maps the old integer/global schema to the new schema
(remapping ids parent → child), preserving `fsrs_state` / `due` / `saved` / proficiency scores,
and folds the legacy `settings` into `user_settings`. It uses a **privileged** (`postgres`)
connection — RLS blocks the request-path role from writing another user's rows — and is
idempotent (natural-key guards per table). Always dry-run first:

```
uv run python scripts/import_sqlite.py --user-id <UUID> --dry-run   # plan only, writes nothing
uv run python scripts/import_sqlite.py --user-id <UUID>             # real import
```

`--sqlite-path` defaults to `data/lengua.db`; `--database-url` defaults to `$DATABASE_URL`. The
full operator procedure is in [`docs/runbook.md`](../../docs/runbook.md) ("Historical data import").

## Account lifecycle (export + delete)

Two store-compliance / GDPR endpoints, both scoped strictly to the authenticated user (no user-id
parameter — the id comes from the verified JWT):

- `GET /account/export` — a downloadable JSON bundle of everything the user owns (profile,
  languages, cards, reviews, proficiency, settings), assembled read-only via the repositories.
- `DELETE /account` — hard-deletes the user's Supabase `auth.users` record via the **service-role
  Auth Admin API**; the `auth.users → profiles → domain` `ON DELETE CASCADE` chain removes the
  profile and all domain data atomically. The auth-user delete is the single irreversible step and
  runs last, so a failure deletes nothing and returns `502` (retryable) — no partial state.

The deletion path needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (a **server-only** secret,
never shipped to the client); without them it fails closed. Both are sourced automatically from
`supabase status` for a local stack.

## Configuration

Settings are read from the environment (and an optional `.env`) via `app/settings.py`. The
documented variables live in the repo-root [`.env.example`](../../.env.example) — copy it to
`.env` and fill in real values. `LLM_PROVIDER` defaults to `groq` and `GROQ_MODEL` to
`llama-3.1-8b-instant` for all dev/CI.
