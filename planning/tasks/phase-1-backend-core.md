# Phase 1 — Backend core (FastAPI + Postgres, no auth yet)

> **Effort:** L  ·  **Depends on:** Phase 0 complete  ·  **Unlocks:** Phase 2
> **Source:** roadmap Phase 1 (../02-roadmap.md) · deep dive (../03-backend.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** the full Generate→Save→Review→Discover loop runs behind FastAPI against Postgres for one seeded dev user, with the LLM call behind a provider seam (Groq default) and the OpenAPI schema feeding `packages/api-types`.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 1.1 — Port `lengua/*` into `lengua_core/` (kept pure)  ·  M

_Context: lift the existing domain logic into `apps/api/lengua_core/` with no FastAPI and no SQL, so it stays unit-testable and portable per the porting map in 03-backend.md._

> **Implemented (PR #1.1):** `lengua_core` is now pure — `scheduler`/`proficiency`/`cards`/`config`
> carry no DB. All SQLite the legacy app needs (the connection, schema, languages/settings CRUD,
> and the FSRS/proficiency/card persistence that used to live in these modules) moved to
> `apps/api/legacy_streamlit/` (notably the new `legacy_streamlit/store.py`), keeping the legacy
> Streamlit app runnable. For 1.1.5 the typed `pydantic-settings` already live in
> `app/settings.py` (Phase 0); `lengua_core/config.py` keeps only the non-secret CEFR/level
> tuning constants + the legacy DB path (secrets removed). The per-provider key fail-fast is
> deferred to task 1.2.1 (the real providers); 1.1.5's test asserts the `groq` default and
> fail-fast on an unknown provider.

- [x] **1.1.1** Create `apps/api/lengua_core/` package and move `models.py` + `prompts.py` in unchanged; re-export `GeneratedCard` / `WordNote` from the package root.
      verify: `python -c "from lengua_core import GeneratedCard, WordNote"` exits 0 and `pytest apps/api/tests/test_imports.py` passes.
- [x] **1.1.2** Move `scheduler.py` (FSRS) into `lengua_core/scheduler.py` as pure functions that take per-user limits as arguments (no DB, no globals).
      verify: `pytest apps/api/tests/lengua_core/test_scheduler.py` passes and `grep -rE "import (sqlalchemy|fastapi)|lengua\.db" apps/api/lengua_core/scheduler.py` returns nothing.
- [x] **1.1.3** Move `proficiency.py` into `lengua_core/proficiency.py`; keep `register_review` a pure function returning a new score (no persistence side effects).
      verify: `pytest apps/api/tests/lengua_core/test_proficiency.py` passes and the function has no DB import (`grep -E "sqlalchemy|sqlite|lengua\.db" apps/api/lengua_core/proficiency.py` is empty).
- [x] **1.1.4** Split `flashcards.py`: pure card-building (sentence → recognition + production card pair, tagged `gen_level`) stays in `lengua_core/cards.py`; drop all SQLite persistence calls from it.
      verify: `pytest apps/api/tests/lengua_core/test_cards.py` asserts one `GeneratedCard` yields two cards with directions `recognition` and `production`; `grep -E "sqlite|lengua\.db" apps/api/lengua_core/cards.py` is empty.
- [x] **1.1.5** Convert `config.py` to typed `pydantic-settings` (`lengua_core/config.py` or `app/config.py`) reading env per environment (`ENV`, `LLM_PROVIDER`, provider keys/models, `DATABASE_URL`); remove module-level secret constants.
      verify: `pytest apps/api/tests/test_config.py` loads settings from a patched env and asserts defaults (`LLM_PROVIDER == "groq"`); app refuses to import settings when a required var for the selected provider is missing.

## 1.2 — LLM provider seam (Groq default, Gemini reserved)  ·  M

_Context: one `llm` interface picked by `LLM_PROVIDER`; default `groq` (OpenAI-compatible JSON mode), with the existing `gemini` impl behind the same interface — flipping providers is a config change, never code._

- [x] **1.2.1** Define `lengua_core/llm/base.py`: a `Provider` protocol with `generate_cards` / `suggest_new_words` / `explain_word`, all returning the existing Pydantic models, plus `get_provider()` that reads `LLM_PROVIDER` once and fails fast if the selected provider's key is unset.
      verify: `pytest apps/api/tests/llm/test_get_provider.py` asserts an unknown `LLM_PROVIDER` raises at startup and a missing `GROQ_API_KEY` (with provider `groq`) raises a clear error.
- [x] **1.2.2** Implement `lengua_core/llm/groq.py` (default): OpenAI-compatible client in JSON mode for `generate_cards`, parsing the JSON response into `list[GeneratedCard]` (incl. `word_notes` → `WordNote`).
      verify: `pytest apps/api/tests/llm/test_groq_generate.py` feeds a recorded JSON payload through the parser and asserts a valid `GeneratedCard` list; no live network in the test.
- [x] **1.2.3** Add Groq `suggest_new_words` and `explain_word` in JSON/text mode, returning `list[str]` and a string respectively, matching the Gemini signatures.
      verify: `pytest apps/api/tests/llm/test_groq_discover_explain.py` parses recorded responses into a word list and an explanation string.
- [x] **1.2.4** Port the existing Gemini impl to `lengua_core/llm/gemini.py` behind the same `Provider` protocol, unchanged logic (native schema-parsed output), selectable via `LLM_PROVIDER=gemini`.
      verify: `LLM_PROVIDER=gemini` with a fake `GEMINI_API_KEY` makes `get_provider()` return the Gemini impl; `pytest apps/api/tests/llm/test_provider_switch.py` passes.
- [x] **1.2.5** Preserve retry/backoff (transient 429/5xx) in a shared helper used by both providers; cap output tokens and words-per-request at the call boundary.
      verify: `pytest apps/api/tests/llm/test_retry.py` simulates two 503s then success and asserts exactly three attempts with backoff (no real sleeps — patched clock).

## 1.3 — SQLAlchemy 2.x persistence + repository/service boundary  ·  L

_Context: replace the SQLite layer with an async SQLAlchemy 2.x layer; routers → services → repositories → DB, with `lengua_core` staying DB-agnostic._

> **Implemented (group 1.3a, tasks 1.3.1 + 1.3.2):** the async persistence foundation lives under
> `app/db/` (inside the ruff + mypy `--strict` + coverage gate; `lengua_core` stays SQL-free):
> `app/db/session.py` (lazy process-wide async engine + `async_sessionmaker` + `get_db`
> dependency + `dispose_engine`; `async_dsn()` rewrites the stored `postgresql://` DSN to
> `postgresql+asyncpg://`), `app/db/base.py` (`DeclarativeBase` with a Postgres naming
> convention), and `app/db/models.py` (SQLAlchemy 2.0 typed `Mapped[]` models for all eight
> tables — profiles, languages, cards, reviews, proficiency, user_settings **plus** llm_usage +
> llm_budget — matching `supabase/migrations/20260621000000_initial_schema.sql` exactly). Two
> deliberate Phase-1 choices: (a) `profiles.id` is a plain `uuid` PK with **no** `auth.users` FK
> (the auth FK + RLS are Phase-2 Supabase concerns); (b) the cost-guard tables are `llm_usage` /
> `llm_budget` (the committed provider-agnostic names), superseding the stale `gemini_*` names in
> the 1.4.3 task text. A reusable async `db_session` pytest fixture (own engine, outer
> transaction rolled back per test via `join_transaction_mode="create_savepoint"`) is in
> `tests/conftest.py` for groups 1.3b/1.5. Deps added: `sqlalchemy[asyncio]`, `asyncpg`,
> `pytest-asyncio`.

- [x] **1.3.1** Add the async SQLAlchemy engine + sessionmaker (`asyncpg`) and a `get_db` session dependency reading `DATABASE_URL`.
      verify: `pytest apps/api/tests/db/test_session.py` opens a session against a throwaway Postgres (testcontainers/local Supabase) and runs `SELECT 1`.
- [x] **1.3.2** Define ORM models for `profiles`, `languages`, `cards`, `reviews`, `proficiency`, `user_settings` with `user_id UUID`, `timestamptz`, `jsonb` columns, real FKs (`ON DELETE CASCADE`), and per-user uniqueness (`languages` UNIQUE `(user_id, name)`; `user_settings` PK `(user_id, key)`).
      verify: `pytest apps/api/tests/db/test_models_metadata.py` asserts column types (UUID/timestamptz/jsonb), the FKs, and the unique constraints exist on `Base.metadata`.
> **Implemented (group 1.3b, tasks 1.3.3–1.3.6):** the repository + service layers now sit on top
> of 1.3a (all inside the ruff + mypy `--strict` + coverage gate). `app/repositories/`
> (`languages`, `cards`, `reviews`, `proficiency`, `settings`) is the **only** code that touches
> the DB — async, SQLAlchemy 2.0, every method scoped by `user_id`, no transaction control (they
> `flush`; the service owns the commit). `app/services/` (`languages`, `generate`, `review`,
> `discover`, `proficiency`, `settings`) orchestrates the pure `lengua_core` (scheduler /
> proficiency / cards / prompts via the provider) + repositories and emits **no** SQL
> (`grep -rE "\bselect\(|\.execute\(" app/services/` is empty). `GenerateService` does
> Generate→Save (band looked up from proficiency, threaded to the provider; each saved card gets
> its own fresh FSRS state); `ReviewService.grade` reschedules + logs the review + nudges
> proficiency atomically; `DiscoverService` suggests-then-accepts into generate. Domain errors
> live in `app/services/errors.py` (`NotFoundError`/`ValidationError`); cards repo input is the
> `NewCard` dataclass. New tests under `tests/repositories/` + `tests/services/` are
> `@pytest.mark.integration` (need the seeded demo user / local Supabase; run in CI). Added a
> `make_new_card` factory.

- [x] **1.3.3** Implement `repositories/languages.py` + `repositories/cards.py` (the only modules that touch the DB) with create/list/delete + save-cards methods, all taking `user_id` explicitly.
      verify: `pytest apps/api/tests/repositories/test_cards_repo.py` saves a pair of cards for the seeded user and reads them back scoped by `user_id`.
- [x] **1.3.4** Implement `repositories/reviews.py` + `repositories/proficiency.py` (insert a review row, upsert proficiency) scoped by `user_id`.
      verify: `pytest apps/api/tests/repositories/test_reviews_repo.py` grades a card, asserts a `reviews` row and an upserted `proficiency` row for that user.
- [x] **1.3.5** Implement `repositories/settings.py` (per-user key/value) with read-all + upsert.
      verify: `pytest apps/api/tests/repositories/test_settings_repo.py` upserts then reads back a daily-limit setting for the seeded user.
- [x] **1.3.6** Build the service layer (`services/languages.py`, `services/generate.py`, `services/review.py`, `services/discover.py`, `services/proficiency.py`, `services/settings.py`) that orchestrates `lengua_core` + repositories and never emits raw SQL.
      verify: `pytest apps/api/tests/services/test_generate_service.py` runs Generate→Save with a stubbed provider and the real repos; `grep -rE "\bselect\(|\.execute\(" apps/api/services/` returns nothing (SQL only in repositories).

## 1.4 — Alembic + first migration (full schema)  ·  M

_Context: Alembic owns the schema; the first migration is the entire multi-tenant schema, applied to a clean Postgres with a downgrade round-trip._

> **Implemented (group 1.4):** Alembic lives at `apps/api/migrations/` with an **async** `env.py`
> that targets `app.db.Base.metadata` and resolves the URL at runtime from `DATABASE_URL` (via
> `app.settings`) — nothing hard-coded in `alembic.ini`; override per-invocation with
> `alembic -x db_url=…`. The first migration (`versions/20260625_0001_initial_schema.py`) is the
> **entire schema**: the 6 app tables (`profiles`, `languages`, `cards` + the
> `(user_id, language_id, saved, due)` index, `reviews`, `proficiency`, `user_settings`) **plus**
> the two cost-guard tables. Per the committed Supabase schema these are named **`llm_usage`
> (PK `user_id, day, kind`) / `llm_budget` (PK `day`)** — the provider-agnostic names that
> supersede the stale `gemini_usage` / `gemini_budget` in the 1.4.3 task text. The migration is
> applyable on a **bare Postgres** (`profiles.id` is a plain `uuid` PK, no `auth.users` FK, no
> RLS); the auth FK + RLS + `handle_new_user` trigger remain Supabase-migration / Phase-2 concerns,
> and `alembic check` confirms the migration carries zero drift vs the ORM. `migrations/` sits
> outside the ruff/mypy/coverage gate. The dev-user seed is `scripts/seed_dev_user.py` (fixed
> `DEV_USER_ID` == `factories.DEMO_USER_ID`): direct `profiles` insert on a bare Alembic DB, and
> on Supabase it first creates the backing `auth.users` row with the same fixed id via the Auth
> Admin API. Tests (`tests/db/test_schema_roundtrip.py`, `tests/db/test_seed_dev_user.py`,
> `tests/db/alembic_helpers.py`) run alembic against a throwaway database created/dropped per test.

- [x] **1.4.1** Configure Alembic (`apps/api/migrations/`, `env.py` async, target `Base.metadata`, `DATABASE_URL` from settings).
      verify: `alembic current` runs against a throwaway Postgres without error and reports an empty/initial state.
- [x] **1.4.2** Author the first migration = full schema: `profiles`, `languages`, `cards` (+ index on `(user_id, language_id, saved, due)`), `reviews`, `proficiency`, `user_settings`, with UUID/timestamptz/jsonb types and the FKs/constraints from 1.3.2.
      verify: on a clean DB, `alembic upgrade head` then `alembic downgrade base` then `alembic upgrade head` all succeed (round-trip); a `pytest apps/api/tests/db/test_schema_roundtrip.py` asserts every expected table exists after upgrade.
- [x] **1.4.3** Add the `gemini_usage` (PK `user_id, day, kind`) and `gemini_budget` (PK `day`) tables to the migration — built now, used by the Phase 3 quota gate. _(Built as `llm_usage` / `llm_budget` — the provider-agnostic names from the committed Supabase schema.)_
      verify: `alembic upgrade head` on a clean DB creates both tables (`\dt` lists them) and `alembic downgrade base` drops them cleanly; round-trip `upgrade→downgrade→upgrade` succeeds.
- [x] **1.4.4** Add a seeded dev-user mechanism (a fixed dev UUID profile inserted via an idempotent seed script / data migration, used as `current_user` until Phase 2).
      verify: running the seed against a fresh `alembic upgrade head` DB yields exactly one `profiles` row with the dev UUID; re-running is idempotent (still one row).

## 1.5 — FastAPI app + routers for the full loop  ·  L

_Context: routers for the whole API surface in 03-backend.md, wired to services; `current_user` resolves to the seeded dev user for now (no JWT until Phase 2)._

- [ ] **1.5.1** Create the FastAPI app (`app/main.py`) + `app/deps.py` with `get_db` and a `current_user` dependency that returns the seeded dev UUID (placeholder for Phase 2 JWT).
      verify: `curl -s localhost:8000/health` returns 200 with `{"status":"ok"}`; `pytest apps/api/tests/api/test_health.py` passes.
- [ ] **1.5.2** `languages` router: `GET/POST/DELETE /languages` (list/add/remove, toggle `vowelized`), scoped to `current_user`.
      verify: `pytest apps/api/tests/api/test_languages.py` POSTs a language, GETs it back, DELETEs it (200/200/204) against a throwaway Postgres.
- [ ] **1.5.3** `generate` router: `POST /generate {words, language_id}` → calls the generate service (stubbed provider in tests) → returns created (unsaved) cards.
      verify: `pytest apps/api/tests/api/test_generate.py` posts two words with a fake provider and asserts the response contains two cards per sentence with `gen_level` set.
- [ ] **1.5.4** `cards` router: `POST /cards/save` persists generated recognition+production cards into the deck for `current_user`.
      verify: `pytest apps/api/tests/api/test_cards_save.py` saves a generated batch then asserts the rows exist (`saved=true`) scoped to the dev user.
- [ ] **1.5.5** `review` router: `GET /review/due` (new vs due split) and `POST /review/{card_id}/grade` (Again/Hard/Good/Easy → FSRS reschedule + proficiency nudge).
      verify: `pytest apps/api/tests/api/test_review.py` grades a due card, asserts the card's `due` moved forward and a `reviews` row + proficiency change were recorded.
- [ ] **1.5.6** `discover` router: `POST /discover {topic?, count?}` → provider suggests new words (preview) → accept path feeds generate.
      verify: `pytest apps/api/tests/api/test_discover.py` with a fake provider returns a preview word list and the accept path produces cards.
- [ ] **1.5.7** `explain` router: `POST /explain {word, sentence, translation, language_id}` → tap-a-word explanation, persisted/cached in `word_explanations`.
      verify: `pytest apps/api/tests/api/test_explain.py` returns an explanation and a second identical call is served from cache (provider called once — assert via mock call count).
- [ ] **1.5.8** `proficiency` router: `GET/PUT /proficiency/{language_id}` (read level + manual override).
      verify: `pytest apps/api/tests/api/test_proficiency.py` PUTs an override and GETs the new score back.
- [ ] **1.5.9** `settings` router: `GET/PUT /settings` (per-user daily limits, discover count).
      verify: `pytest apps/api/tests/api/test_settings.py` PUTs a daily-limit value and GETs it back unchanged.
- [ ] **1.5.10** End-to-end loop integration test: Generate → Save → due appears in Review → grade → Discover, all over HTTP for the seeded user.
      verify: `pytest apps/api/tests/api/test_full_loop.py` walks the whole loop against a throwaway Postgres and asserts a 200 at each step with a graded card showing a future `due`.

## 1.6 — OpenAPI schema + `packages/api-types` codegen  ·  S

_Context: the FastAPI OpenAPI schema is the contract for the typed TS client; keep it stable so the generated client stays in sync._

- [ ] **1.6.1** Add a script that dumps the live OpenAPI schema to a checked-in `apps/api/openapi.json`.
      verify: `python apps/api/scripts/dump_openapi.py` writes `openapi.json`; a CI check (`pytest apps/api/tests/test_openapi_stable.py`) fails if the committed file is stale vs the app's current schema.
- [ ] **1.6.2** Wire `packages/api-types` codegen from `openapi.json` (e.g. `openapi-typescript`) producing typed models/client.
      verify: `pnpm --filter api-types generate` regenerates types with no diff against the committed output; `pnpm --filter api-types build` (or `tsc --noEmit`) passes.

## 1.7 — Observability + structured logging skeleton  ·  S

_Context: instrumentation STARTS here per the roadmap (dashboards/alerts land in Phase 5). Wire the hooks now: auto-instrument FastAPI/SQLAlchemy/httpx and structured JSON logs._

- [ ] **1.7.1** Add OpenTelemetry SDK wiring in `app/main.py` with auto-instrumentation for FastAPI, SQLAlchemy, and httpx; OTLP endpoint/headers read from env (no-op exporter when unset so local/CI don't fail).
      verify: `pytest apps/api/tests/obs/test_otel_wiring.py` asserts spans are emitted to an in-memory span exporter for one `/health` request (an HTTP server span exists).
- [ ] **1.7.2** Add a structured JSON logging skeleton (one log line per request with method, path, status, latency) and a `trace_id` field placeholder for correlation.
      verify: `pytest apps/api/tests/obs/test_logging.py` captures a request log line, parses it as JSON, and asserts `method`, `status`, `latency_ms`, and a `trace_id` key are present.

---

## Phase 1 exit gate

Phase 1 is DONE only when all of these hold:

- [ ] The full Generate→Save→Review→Discover loop works over HTTP for the seeded dev user — verify: `pytest apps/api/tests/api/test_full_loop.py` is green against a throwaway Postgres.
- [ ] The schema is Alembic-managed and reversible — verify: on a clean DB, `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` all succeed and every table from 1.4.2/1.4.3 exists.
- [ ] `lengua_core` is pure (no FastAPI, no SQL) and SQL lives only in `repositories/` — verify: `grep -rE "fastapi|sqlalchemy|asyncpg" apps/api/lengua_core/` and `grep -rE "\.execute\(|select\(" apps/api/services/` both return nothing.
- [ ] The LLM seam works as a config flip — verify: `pytest apps/api/tests/llm/test_provider_switch.py` proves `LLM_PROVIDER=groq` and `LLM_PROVIDER=gemini` each load the right impl with no code change, default `groq`.
- [ ] The OpenAPI schema generates the TS client cleanly — verify: `python apps/api/scripts/dump_openapi.py` + `pnpm --filter api-types generate` produce no diff and the package builds.
- [ ] Observability hooks are live — verify: `pytest apps/api/tests/obs/test_otel_wiring.py` and `test_logging.py` pass (spans emitted, JSON logs with `trace_id`).
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
