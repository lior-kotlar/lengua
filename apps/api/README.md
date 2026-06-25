# apps/api — Lengua API (FastAPI)

The FastAPI backend service, managed with [`uv`](https://docs.astral.sh/uv/) on Python 3.12.

## Structure

- `app/` — HTTP layer: `main.py` (FastAPI app + `GET /health`), `settings.py`
  (pydantic-settings config). Routers, auth, quota, and OTel wiring land in Phase 1.
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
- `scripts/` — dev/ops scripts: `verify.py` (the local gate) and `seed_e2e.py` (E2E demo-account seeder).
- `tests/` — pytest suite. Unit tests (`test_health.py`, `test_settings.py`, `test_factories.py`,
  `test_fake_llm.py`) plus DB-backed integration tests (`test_db_fixture.py`, `test_seed.py`).
  Shared fixtures + the Supabase-CLI Postgres wiring live in `conftest.py`; deterministic builders
  in `factories.py`.
- `migrations/` — Alembic (Phase 1+).
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
test runs inside a `SAVEPOINT` that is rolled back at teardown.

The LLM is never called in tests: `FakeLLM` (`LLM_PROVIDER=fake`) is a deterministic, network-free
stand-in (`tests/test_fake_llm.py` runs with `pytest-socket --disable-socket` to prove it).

Seed the deterministic demo/reviewer account (idempotent — creates the auth user via the Supabase
Auth Admin API, then a language + a set of due cards) for E2E:

```
uv run python scripts/seed_e2e.py
```

## Configuration

Settings are read from the environment (and an optional `.env`) via `app/settings.py`. The
documented variables live in the repo-root [`.env.example`](../../.env.example) — copy it to
`.env` and fill in real values. `LLM_PROVIDER` defaults to `groq` and `GROQ_MODEL` to
`llama-3.1-8b-instant` for all dev/CI.
