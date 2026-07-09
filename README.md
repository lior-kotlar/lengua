# Lengua 🗣️

A personal language-learning app. You type the vocabulary words you want to learn, and
Lengua asks Gemini for natural example sentences that use them — then turns those
sentences into flashcards and schedules a smart daily review batch.

It replaces the manual workflow of pasting words + a long "rules" prompt into a chat UI:
the rules, the generation instruction, and your active language are attached
automatically on every request, so you only ever supply the words.

## Repository layout & how to run each app

Lengua is being productionized from a single Streamlit app into a monorepo (FastAPI API +
React web app + Supabase + Cloud Run). The open work lives in [`planning/`](planning/) — start
at [`planning/README.md`](planning/README.md).

```
apps/
  api/        FastAPI service (uv) — scaffolded in Phase 0 group 0.2
  web/        React + TS + Vite app (pnpm, Tailwind + shadcn/ui) — group 0.3
packages/
  api-types/  OpenAPI-generated TS types + typed client for the API (Phase 1.6)
infra/        infra & CI/CD docs (the CI gate lives in .github/workflows/)
docs/         privacy policy, runbook, legal — group 0.8
planning/     productionization plan & per-phase task files
supabase/     Supabase CLI config, initial migration, seed
```

`apps/web` and `packages/*` form a single **pnpm workspace** (`pnpm-workspace.yaml` at the repo
root, one root `pnpm-lock.yaml`). `apps/api` is a separate uv/Python project.

| App | Location | How to run | Status |
| --- | --- | --- | --- |
| API | `apps/api/` | `cd apps/api && uv sync && uv run uvicorn app.main:app` (serves `GET /health`); verify with `uv run python scripts/verify.py` | runnable now |
| Web | `apps/web/` | `pnpm install` (at the repo root — pnpm workspace), then `cd apps/web && pnpm dev` (app shell + auth: signup/login/reset/OAuth, session gating — every password field has an in-box **show/hide ("eye") toggle** (hold to reveal on mouse/touch, Enter/Space to toggle for keyboard); a real **Dashboard** home screen — a "Today" hero with your due-card count (counting up) and a **Start review** pill (or an all-caught-up state that points at Generate/Discover), a per-language tile grid (CEFR band chip + progress bar + a due badge; tapping a tile sets that language active and jumps into Review), quick actions to Generate/Discover, and a three-step onboarding card for a fresh account — all from existing read APIs; active-language picker + add/remove languages (a language **code** is required when vowel marks are enabled, so right-to-left scripts render in the correct direction and font) + CEFR level panel with manual override; **Generate** — paste words → example sentences → select & save flashcards, with a friendly daily-limit panel on quota; **Review** — the FSRS loop: due batch (new/due counts) → reveal → rate Again/Hard/Good/Easy (locked red/orange/blue/green) → next, with tap-a-word explanations on production cards and space/enter + 1–4 keyboard shortcuts; **Discover** — pick a word count (defaulting to your `discover_count` setting) + optional topic → preview suggested new words → accept (feeds them into Generate) or reroll, sharing the same daily-limit panel; **Settings** — edit your daily new-card limit and daily total-card limit (which bound your review batch) and the Discover word count (validated against the allowed bounds, including new ≤ total) → save, plus a toggle to turn product-analytics consent on/off; **Account** — see your email, sign out, export all your data as a JSON download, or delete your account behind a confirm-typed dialog; **RTL & diacritics** — Arabic/Hebrew languages render the Generate/Review/Discover text right-to-left in diacritic-correct self-hosted fonts (Noto Naskh Arabic / Noto Sans Hebrew, bundled — no CDN), with a **vowel-marks** toggle that shows or strips the harakat/nikkud and an RTL-aware tap-a-word; **consistent UX states** — shared loading skeletons, empty states, and retryable error cards across Generate/Review/Discover, plus a first-class shared daily-limit panel on quota; a first-run **analytics-consent** banner — EU-hosted, anonymized product analytics (PostHog) loads only after you explicitly opt in (and can be toggled any time in Settings), the choice is remembered, and nothing analytics-related loads or is sent otherwise (and only with a `VITE_POSTHOG_KEY` configured); copy `apps/web/.env.example` to `.env`); verify with `pnpm verify`; E2E via `pnpm exec playwright test` | runnable now |
| API types | `packages/api-types/` | `pnpm gen:api` (root convenience for `pnpm --filter api-types generate` — re-derive TS types + runtime `schemaLimits` constants from `apps/api/openapi.json`) · `pnpm --filter api-types build` (typecheck) | runnable now |
| Legacy Streamlit | `apps/api/legacy_streamlit/` | `cd apps/api && streamlit run legacy_streamlit/app.py` | **deprecated — retained for reference** (still runnable) |

### API endpoints (Phase 1 — full loop)

Beyond `GET /health`, the FastAPI service serves the whole Generate→Save→Review→Discover loop
over HTTP. The backend **verifies a Supabase access token (JWT) on every request** (Phase 2.3):
the `current_user` dependency checks the token's signature, `exp` and `aud` and derives the user
id from `sub` — HS256 against `SUPABASE_JWT_SECRET` by default, or RS256/ES256 via a configured
`SUPABASE_JWKS_URL`. Requests with a missing/invalid token get `401`; only the unauthenticated
infra probes `GET /health` (liveness) and `GET /ready` (readiness — a plain `SELECT 1` for DB
connectivity, `503` when the DB is unreachable) are open.
A strict **CORS allowlist** (`CORS_ALLOW_ORIGINS`, defaulting to local web origins + the Capacitor
scheme) fronts the API. For local work, point `DATABASE_URL` at a Postgres (e.g. the local
Supabase CLI stack), seed it with `uv run python scripts/seed_dev_user.py`, and send
`Authorization: Bearer <token>` (a JWT signed with the project's `SUPABASE_JWT_SECRET`).

**Tenant isolation is enforced twice (Phase 2.6).** On top of the app-layer `WHERE user_id = …`
scoping, every per-user table has Postgres **Row-Level Security** (`using (user_id = auth.uid())`;
`profiles` keys on `id`), so an app-code bug still cannot leak data across tenants. To make those
policies bite, each request's DB session assumes the non-privileged `authenticated` role and
publishes the caller's `request.jwt.claims` (`SET LOCAL ROLE` + `set_config`, re-applied on every
transaction) — see [`app/db/rls.py`](apps/api/app/db/rls.py), wired through `app/deps.get_db`.
Migrations and seed scripts keep their privileged connections (they must bypass RLS), so the
backend's `DATABASE_URL` should point at a Supabase-provisioned Postgres where the `authenticated`
role and `auth.uid()` exist. The policies live in `supabase/migrations/…` and are reproduced for
the backend's own schema by Alembic revision `0003`.

A `profiles` row (`plan='free'`) is created automatically for every user on first signup by the
`handle_new_user` Postgres trigger (defined in `supabase/migrations/…` and reproduced for the
backend's own schema by Alembic revision `0002`) — no guest/anonymous mode
(`enable_anonymous_sign_ins = false`). A ready-to-use **demo / reviewer account** (for App Store /
Play review or a quick manual run) is provisioned by `uv run python scripts/seed_e2e.py`: it
admin-creates a pre-confirmed Supabase auth user (`demo@lengua.test` / `demo-password-123`) with a
Spanish deck of due cards, so signing in with those credentials immediately exercises the full
review loop.

The operator's pre-productionization history (the legacy single-user `apps/api/data/lengua.db`) can
be imported into a real account with `uv run python scripts/import_sqlite.py --user-id <UUID>`
(dry-run first; idempotent; preserves FSRS state, due dates, and proficiency) — see the
[runbook](docs/runbook.md) "Historical data import" section.

**Supabase Auth configuration** lives in the version-controlled, CLI-read repo-root
[`supabase/config.toml`](supabase/config.toml): email/password signup requires **email
confirmation** (`enable_confirmations`) and enforces a **password policy**
(`minimum_password_length = 8`, lower- + upper-case letters and digits); `site_url` +
`additional_redirect_urls` form the post-auth **redirect allow-list** (local/staging/prod web
origins + `capacitor://localhost` + the `app.lengua://` deep-link scheme); and the confirmation /
password-reset / magic-link emails render branded templates under
[`supabase/templates/`](supabase/templates). Google OAuth is scaffolded (env-wired, inert until the
owner supplies credentials) and Apple is documented for later — the owner setup steps (OAuth
credentials + custom SMTP) are in [`infra/supabase/oauth-setup.md`](infra/supabase/oauth-setup.md).
(Admin-created accounts such as the demo/reviewer user bypass email confirmation, so the seeded
flows above keep working.)

| Method + path | Purpose |
| --- | --- |
| `GET /me` | The authenticated user's account overview: identity (`id`, `email_verified`) from the verified token, profile `plan`, and per-language proficiency levels (`score`/`band`/`progress`) — scoped to that user only. |
| `GET/POST/DELETE /languages`, `PATCH /languages/{id}` | List/add/remove a language. `POST` is idempotent on the per-user name and returns a `created` flag (a re-add returns the existing row unchanged, so its level is never reset); `PATCH` edits `name`/`code`/`vowelized` (partial). |
| `POST /generate` | `{language_id, words}` → recognition+production card previews (unsaved). |
| `POST /cards/save` | Persist generated previews into the deck (`saved=true`). |
| `GET /review/due?language_id=` | Today's due batch, split into `new` vs. `due`. |
| `POST /review/{card_id}/grade` | `{rating: 1..4}` (Again/Hard/Good/Easy) → FSRS reschedule + proficiency nudge. |
| `POST /discover` | `{language_id, count?, topic?}` → preview new words at the learner's level (excludes known vocab). |
| `POST /discover/accept` | `{language_id, words}` → generate + save cards for the accepted words. |
| `POST /explain` | `{word, sentence, translation, language_id}` → tap-a-word explanation, cached in `cards.word_explanations`. |
| `GET/PUT /proficiency/{language_id}` | Read the CEFR level (score/band/progress); `PUT` overrides it by `score` or `band`. |
| `GET/PUT /settings` | Read/upsert per-user preferences as a `{key: value}` map: the daily review limits `daily_new_limit` / `daily_total_limit` (which bound the `GET /review/due` batch — each falling back to the server default when unset) and the Discover word count `discover_count`. `PUT` merges the supplied keys; a key set to `null` is **removed**. The typed numeric keys are bounds-checked and `daily_new_limit ≤ daily_total_limit` is enforced (else `422`). |
| `GET /account/export` | Download a JSON bundle of **all** your data (profile, languages, cards, reviews, proficiency, settings), scoped to you — for store/GDPR data export. |
| `DELETE /account` | **Hard-delete** your account: removes your Supabase auth user via the service-role Admin API, which cascades your profile and all domain data away (no orphans). No body; acts only on the token's user. |
| `POST /account/deletion-request` | **Public** (no auth): the external deletion path (Play requirement). `{email}` → a generic, non-enumerating ack; if the email has an account, emails a signed one-hour token. Rate-limited per email. |
| `POST /account/deletion-confirm` | **Public** (no auth): `{token}` from the emailed link → runs the same cascade delete as `DELETE /account`. Ownership is proven by the token, not a session. |
| `GET /feature-flags` | **Public** (no auth): the resolved PUBLIC feature-flag map (`{name: enabled}`, secrets-free). The web reads it to gate dark UI. |

The active LLM provider is chosen by `LLM_PROVIDER` (`groq` default; `fake` for tests/E2E).

The web app also serves three **public pages** (no login): `/privacy` (the GDPR privacy policy),
`/support`, and `/delete-account` (the external account-deletion form), linked from the footer and the
Account screen.

**Feature flags (ship dark, toggle without a redeploy).** Risky/new features hide behind a flag
that defaults **off**, resolved by [`app/feature_flags.py`](apps/api/app/feature_flags.py) from an
env default (`FEATURE_*`) overlaid by a row in a small **global** `feature_flags` table, cached
in-process for `FEATURE_FLAG_TTL_SECONDS` (default 30). Writing the table row flips the flag for
everyone within one TTL with **no redeploy**; the `feature_flags` table is operator config locked
down to the server (REVOKE from `authenticated`/`anon` + deny-by-default RLS — a user can never
enable their own flags), and only the resolved PUBLIC map reaches the browser via
`GET /feature-flags`. The experimental **word of the day** surface (the JWT-protected, flag-gated
`GET /experimental/word-of-the-day` route + a Dashboard card) ships dark behind `word_of_the_day`
(off by default) — `404`/absent until the flag is on.

**DB-backed prompts (tweak a prompt without a redeploy).** The LLM prompt fragments (the numbered
rules block, the generation/vocalization/level instructions, the output-format spec, and the
Discover suggestion template) live in an append-only, versioned **global** `prompt_versions` table,
resolved by [`app/prompt_store.py`](apps/api/app/prompt_store.py). Generation always uses the
**active** version per fragment, cached in-process for `PROMPT_CACHE_TTL_SECONDS` (default 60), so
appending a new active row changes generation for everyone within one TTL with **no redeploy** (and
you can roll back by moving the active pointer to an older version). The builders keep all assembly +
interpolation in code and fall back to the in-code defaults in
[`lengua_core/prompts.py`](apps/api/lengua_core/prompts.py) when the table is empty/unreachable — so
the legacy Streamlit app and CI/E2E (FakeLLM) work with zero DB dependency. Like `feature_flags`,
`prompt_versions` is operator config locked down to the server (REVOKE from `authenticated`/`anon` +
deny-by-default RLS — never reachable by a client). Adding a version today is a SQL `INSERT`
(active-pointer move); an admin UI is a follow-up.

**Usage & cost limits.** Every LLM request passes a gate chain before the provider is called, in
order **email-verified → rate-limit → daily-cap → global-budget**; the earliest failure is the one
returned.

- **Email verified first.** Generation requires a verified email — an unverified account gets
  **HTTP 403** `{"code": "email_unverified"}` and no provider call.
- **Per-user rate limit.** A sliding window caps gated LLM requests per user per minute across all
  kinds (`RATE_LIMIT_PER_MIN`, default 10). Over it, the API returns **HTTP 429**
  `{"code": "rate_limited"}` with a `Retry-After` header (seconds until the window frees). The
  limiter is in-process today (single instance); the distributed swap for multi-instance is a
  Phase-6 task.
- **Per-user daily cap** per kind (`generate` / `discover` / `explain`; `/discover/accept` counts as
  `generate`). A user's own cap (settings `daily_cap_generate` / `daily_cap_discover` /
  `daily_cap_explain`) is clamped by a hard server maximum, with a generous default when unset — all
  env-configurable (`MAX_*_PER_DAY` / `DEFAULT_*_PER_DAY`). At/over the cap, the endpoint returns
  **HTTP 429** `{"code": "daily_cap_reached", "kind": "<kind>"}`.
- **New-account guard.** A freshly-created account gets a reduced first-day `generate` ceiling
  (`NEW_ACCOUNT_DAY0_GENERATE_CAP`, default 5) so signup-spam can't drain the shared key on day one;
  established accounts use their normal cap.
- **Request-size cap.** A `/generate` word list over `MAX_WORDS_PER_REQUEST` (default 30) is rejected
  with **HTTP 422** at the API boundary — a hard reject, not silent truncation — so an oversized
  prompt never reaches the provider. Each allowed call also passes a max output-token cap to the
  provider so an answer can't balloon in cost.
- **Discover reuse.** A repeated `/discover` for the same language + topic (+ count) within
  `DISCOVER_REUSE_WINDOW_SECONDS` (default 300) returns the prior preview from an in-process cache —
  no new LLM call and no count. The cache is in-process today (single instance); a repeat landing on
  a different instance simply misses, and the distributed swap is a Phase-6 task.
- **Global daily kill-switch.** The backstop that guarantees the operator key can never produce a
  bill: a project-wide ceiling on **successful** LLM calls per day across *all* users
  (`GLOBAL_DAILY_BUDGET`, default 1000, set below the active provider's free requests-per-day). Once
  the day's budget is spent, *every* user gets **HTTP 429**
  `{"code": "daily_limit_reached", "message": "Daily limit reached, please try again tomorrow."}`
  until the UTC day rolls over.
- **Concurrency cap.** A process-wide limit bounds how many provider calls run at once
  (`LLM_MAX_CONCURRENCY`, default 4) so a burst can't flood the free tier (the blocking provider call
  runs in a worker thread, so the event loop stays responsive). Under sustained load, once the cap is
  full and no slot frees within a short wait, the request gets **HTTP 503**
  `{"code": "server_busy", "message": "The server is busy, please try again in a moment."}` with a
  `Retry-After` header — never an unbounded queue.
- **Transient-error backoff.** A provider 429/5xx is retried a few times with exponential backoff +
  jitter; if it *persists*, the request surfaces the same friendly **HTTP 503** `server_busy`
  response rather than an opaque error.

Caps count only **successful** provider calls; cached responses cost nothing (no gate, no count) —
both `/explain` (its persisted `word_explanations`) and a repeated `/discover` (the short reuse
window) serve from cache, so only a cache miss is gated and counted. Every gated call emits an
OpenTelemetry span + metrics carrying the cap-hit gate and remaining budget (see
[Observability](#observability-traces--structured-logs)). All limits are in
[`.env.example`](.env.example).

### API contract & typed client (`packages/api-types`)

The FastAPI OpenAPI schema is the contract the web app's typed client is generated from. It is
checked in as `apps/api/openapi.json` and kept in lockstep by two CI drift checks:

```bash
python apps/api/scripts/dump_openapi.py   # rewrite apps/api/openapi.json from the live app
pnpm gen:api                              # re-derive packages/api-types/src/{schema,constants}.ts from it
```

Regenerate both whenever the HTTP surface changes (routers/schemas). CI fails the PR if
`openapi.json` is stale versus `app.openapi()` (`tests/test_openapi_stable.py`) or if the
generated TS sources are stale versus `openapi.json` (a `git diff` check on `schema.ts` +
`constants.ts`). `packages/api-types` exports the generated `paths` / `components` / `operations`
types plus a typed `openapi-fetch` client via `createApiClient(...)` and the `ApiClient` type, and
`schemaLimits` — runtime numeric constraints (e.g. the `POST /generate` word cap) that the TS types
cannot carry, extracted from the schema for client-side validation.

The web app calls the backend exclusively through this client. `apps/web/src/lib/api-client.ts`
wraps it into a lazy authed singleton (`getApiClient()`) whose middleware injects
`Authorization: Bearer <token>` from the current Supabase session on every request, plus an
`unwrap()` helper that returns typed data on success or throws a typed `ApiError`
(`{ status, code, message, retryAfter }`) — the shape the cost-guard states surface as friendly,
actionable UI. Supabase is auth-only; all data flows through this client.

### Observability (traces + structured logs)

The API is instrumented from Phase 1 (dashboards/alerts land in Phase 5). `app/observability.py`
(wired from `create_app()`) sets up **OpenTelemetry** tracing with auto-instrumentation for
FastAPI (one server span per route), SQLAlchemy (DB query spans nested under the request), and
httpx (outbound client spans, e.g. the prod Groq/Gemini call), and emits **one structured JSON
access-log line per request** to stdout (`method`, `path`, `status`, `latency_ms`). A correlation
filter stamps **`trace_id` + `span_id` + `user_id`** onto every log record (5.3.2) so logs join to
traces — in-request application logs carry the authenticated `user_id`, while the access line
(emitted in the outer ASGI layer) carries `trace_id`/`span_id` with a `null` `user_id`. Every signal
(traces, metrics **and** logs) is tagged with the `service.name` and `deployment.environment`
resource attributes so Grafana can filter per environment. Traces and logs are exported via OTLP (to
Grafana Cloud Tempo / Loki) **only** when `OTEL_EXPORTER_OTLP_ENDPOINT` (or a signal-specific
variant) is set — locally and in CI it is unset, so export is a no-op with zero network egress; the
stdout JSON line is always emitted (Cloud Run ships it to Loki as the primary path). Configure a
backend purely through the standard env vars (no code change):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway.example/otlp   # enables OTLP trace + metric + log export
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64>          # auth token for Grafana Cloud
OTEL_SERVICE_NAME=lengua-api                                     # service.name (default lengua-api)
DEPLOYMENT_ENVIRONMENT=staging                                   # deployment.environment (default: ENV)
# signal-specific overrides (optional): *_TRACES_ENDPOINT / *_METRICS_ENDPOINT / *_LOGS_ENDPOINT
```

**Cost-guard spans + metrics (Phase 3.8 / 5.2).** Every gated LLM operation also emits one
OpenTelemetry **span** `llm.call` carrying `llm.provider` / `llm.model` / `llm.latency_ms` /
`llm.tokens_in` / `llm.tokens_out` (from the vendor's token usage), `llm.input_size` (words for
generate / count for discover / 1 for explain) and `llm.retry_count` (backoff retries), plus the
cost-guard context `quota.kind`, `quota.cap_hit` (which gate blocked — `email` / `rate` /
`daily_cap` / `global_budget`, or `none`), and `budget.remaining` (`GLOBAL_DAILY_BUDGET − today's
count`). A blocked call records tokens `0` and still emits a complete span. A sibling **`quota.check`
span** (emitted on every gated call, admit and block) carries `user.cap_remaining` +
`budget.remaining`, and **`review.grade`** wraps a graded review with `review.rating` /
`review.next_due` / `review.proficiency_delta`. **Cost metrics:** `llm_calls_total{kind, result}`
(`result` ∈ `success` / `blocked` / `error`), `llm_cap_hits_total{gate}` (the quota-blocks counter —
`gate` is the block reason), `llm_tokens_total{kind, direction}`, and the `llm_budget_remaining`
gauge. **Product metrics:** `reviews_total`, `cards_created_total`, `signups_total`, and the
`active_users` gauge (process-local for now; a Phase-6 distributed store replaces them at scale). The
FastAPI instrumentation also exports a per-route RED **`http.server.duration`** histogram. All names
are provider-agnostic (`llm.*` / `llm_*`, never `gemini.*`). Metrics export via OTLP **only** when an
endpoint is set (the generic `OTEL_EXPORTER_OTLP_ENDPOINT` or the metrics-specific
`OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`), so they too are no-op with zero egress by default.

**Error tracking (Sentry, Phase 5.4).** The backend (`app/error_tracking.py`) and the web app
(`apps/web/src/lib/error-tracking.ts`) report exceptions to **Sentry**, each with its **own** DSN —
and, like the OTLP exporters, Sentry initialises **only** when its DSN is set, so local/CI/E2E load
nothing with zero egress. Set `SENTRY_DSN_API` (backend; `.env`) and the browser-safe,
`VITE_`-prefixed `VITE_SENTRY_DSN_WEB` (web; `apps/web/.env`) to enable them. The backend stamps each
issue with the authenticated `user_id` + the active `trace_id` (so it links to the matching Tempo
trace); the web SDK captures JS errors + Web Vitals/performance. `VITE_ENABLE_DEBUG_TOOLS` (dev/test
only — never set in production) surfaces a hidden debug-error button used to exercise the capture path
in tests.

### One-command verify (local quality gate)

Run the whole monorepo's lint + type-check + tests (+ web build) in one command — it fans out
to the **api** verify (`uv run python scripts/verify.py` in `apps/api`) and the **web** verify
(`pnpm verify` in `apps/web`) and exits non-zero if either fails:

```bash
make verify          # runs apps/api + apps/web gates; targets: verify-api, verify-web
```

No `make` (e.g. on **Windows**)? Run the identical cross-platform engine — it does the same
fan-out and is what CI/local gates call:

```bash
python scripts/verify.py
```

`pnpm` is invoked via `corepack pnpm` when `pnpm` isn't on your `PATH` (corepack ships with
Node and honors the `packageManager` pin in `apps/web/package.json`).

### Deployment (CI/CD)

Two pipelines, both as code under `.github/workflows/`:

- **CI gate** (`ci.yml`, on every PR) — the blocking lint/type/test/build/E2E/security gate.
- **CD** — merging to `main` ships **staging** (`deploy-staging.yml`: build + push the API image to
  Artifact Registry, run a discrete `alembic upgrade head` against staging, deploy Cloud Run
  `lengua-api-staging`, deploy Vercel staging, smoke-check). **Prod** is a separate, gated
  promotion (`deploy-prod.yml`: a `production`-environment approval → promote the exact
  staging-validated image digest to `lengua-api-prod`, gated prod migration, Vercel production,
  smoke-check). A bad release rolls back in one command with
  [`infra/deploy/rollback.sh`](infra/deploy/rollback.sh).

> **CD is gated off by default.** Every deploy job is `if: ${{ vars.DEPLOY_ENABLED == 'true' }}`, so
> with the repo variable unset the workflows are green no-ops (nothing deploys). The owner turns CD
> on with `gh variable set DEPLOY_ENABLED -b true` — see
> [`planning/go-live-activation.md`](planning/go-live-activation.md). Alembic's migration target is
> chosen with `alembic -x env=staging|prod|local` (→ `STAGING_DATABASE_URL` / `PROD_DATABASE_URL` /
> `DATABASE_URL`; a one-off `-x db_url=<dsn>` still overrides). Deploy/rollback/migration runbook:
> [`docs/runbook.md`](docs/runbook.md).

### Legacy Streamlit app — deprecated (retained for reference)

The React web app (`apps/web`) now has **full feature parity** with the original Streamlit app — see
the [Streamlit → React parity checklist](docs/streamlit-parity.md), which maps every legacy
page/feature to its React equivalent (the one exception, the Gemini model selector, is intentionally
retired because the LLM provider/model is now operator/server config). The **legacy Streamlit app is
therefore deprecated and retained for reference only**: the code is **not** being deleted and stays
runnable — as a reference implementation and a fallback — until the React app ships to production
(Phase 6) and is wrapped for mobile (Phase 7). The sections below document that legacy app.

## How it works

1. **Pick a language** in the sidebar (e.g. Spanish, Arabic). It's saved and stays active
   across pages and restarts. You can learn several languages and switch between them. For
   scripts with optional diacritics (Arabic, Hebrew) a per-language **vowel marks** toggle
   asks Gemini to fully vocalize the generated sentences.
2. **Generate** — paste vocabulary words (one per line or comma-separated). Lengua sends
   them to Gemini with your fixed rules prompt and your current level, and gets back, for
   each item:
   - the **sentence** in your target language,
   - a natural **English translation**,
   - the **vocabulary words** it used.
3. **Discover** — no input needed. Lengua looks at all the vocabulary you already know,
   then asks Gemini to pick new words at your current CEFR level that you haven't seen yet.
   You can optionally set a topic (e.g. "food", "travel") to guide the selection, set a
   count, review the suggested words, and either accept them or ask for a different set
   before sentences are written.
4. **Save as flashcards** — each sentence becomes **two** independently-scheduled cards in
   your local SQLite deck: a *recognition* card (read the target sentence, recall the
   English) and a *production* card (read the English, build the target sentence). On the
   production card you can tap any word for a quick explanation.
5. **Review** — Lengua shows the cards due today, you reveal the answer and rate your recall
   (*Again / Hard / Good / Easy*). [FSRS](https://github.com/open-spaced-repetition/py-fsrs)
   reschedules each card, so the daily batch stays fresh on its own — no cron needed. Your
   answers also nudge your level (see below).

## Your level

Each language has a level on the **CEFR scale (A1 → C2)** that tunes how long and complex
the generated sentences are. It's shown in the sidebar (with progress to the next band) and
on the Generate and Review pages.

- **It adapts as you review.** Answering *Easy* nudges your level up; *Again* / *Hard* nudge
  it down; *Good* holds roughly steady — so sentences track your real ability over time.
- **Production counts more.** Because building a sentence (English → target) is harder than
  reading one, success on production cards raises your level faster, and struggling on them
  is penalized less.
- **Only current-level cards move it.** Each card remembers the level it was generated at, so
  a backlog of old/easy cards can't inflate your level.
- **You can override it.** Use *Adjust level* in the sidebar to set your band manually (handy
  when starting a language you already partly know); it keeps adapting from there.

The nudge sizes and weighting are tunable constants in
[`apps/api/lengua_core/config.py`](apps/api/lengua_core/config.py) (`LEVEL_DELTAS`,
`PROD_POS_WEIGHT`, `PROD_NEG_WEIGHT`, `LEVEL_WINDOW`).

## Setup

The Gemini API key is read from a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

Install dependencies (a virtualenv is recommended). `requirements.txt` stays at the
repo root for the legacy app:

```
pip install -r requirements.txt
```

## Run

The legacy Streamlit app now lives under `apps/api/legacy_streamlit/`. Run it from
`apps/api/` so the `lengua_core` package is importable:

```
cd apps/api
streamlit run legacy_streamlit/app.py
```

This opens the app in your browser. Data is stored locally in `apps/api/data/lengua.db`
(created automatically relative to the working directory, git-ignored).

## Customizing the sentence rules

The rules that govern *how* sentences are written live in
[`apps/api/lengua_core/prompts.py`](apps/api/lengua_core/prompts.py) as an editable `RULES`
list. To change them **in code**, edit one entry — the prompt text is reassembled
automatically. In the productionized API these code constants are the **fallback** default: the
active prompt text is read from the versioned `prompt_versions` table (see *DB-backed prompts*
above and [`apps/api/README.md`](apps/api/README.md#db-backed-prompts-prompt_versions)), so a
prompt can also be changed in a running deployment without a code change. The output shape
(sentence / translation / used_words) is enforced by the schema in
[`apps/api/lengua_core/gemini.py`](apps/api/lengua_core/gemini.py), so the rules only affect
writing style, not format.

## Project layout

The domain logic lives in a **pure** `lengua_core/` package (no database, no web framework), and
the legacy Streamlit app — including all of its SQLite persistence — lives under
`legacy_streamlit/`. Both sit under `apps/api/`:

```
apps/api/
  legacy_streamlit/    legacy single-user Streamlit app + its SQLite store
    app.py             Streamlit entry point / home page
    pages/
      1_Generate.py    words in -> sentences out
      2_Review.py      daily flashcard review (FSRS)
      3_Discover.py    auto-pick new vocab at your level -> sentences out
      4_Settings.py    app-wide settings
    db.py              SQLite connection + schema (+ idempotent migrations)
    languages.py       learned languages + active-language setting
    settings.py        per-user app settings (daily limits, discover count, model)
    store.py           SQLite persistence wiring the pure core to the database
    ui.py              shared sidebar (language selector + level)
  lengua_core/         pure domain core — no DB, no FastAPI (unit-testable, portable)
    config.py          non-secret CEFR/level tuning constants + legacy DB path
    models.py          GeneratedCard / WordNote (sentence / translation / used_words / notes)
    prompts.py         the editable rules + output-format + level prompt
    cards.py           pure card-building: one sentence -> recognition + production pair
    scheduler.py       pure FSRS: new-card state, due-batch selection, grading
    proficiency.py     pure CEFR scoring: bands, progress, review-driven nudges
    gemini.py          Gemini provider wrapper: words -> cards; tap-a-word explanations
    llm/               provider seam (base protocol, deterministic fake, selector)
```

## Configuration knobs

Optional environment variables (the `LENGUA_*` knobs live in
[`apps/api/lengua_core/config.py`](apps/api/lengua_core/config.py); `GEMINI_MODEL` is read from
the environment by [`apps/api/lengua_core/gemini.py`](apps/api/lengua_core/gemini.py)):

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model used for generation |
| `LENGUA_DB_PATH` | `data/lengua.db` | SQLite database location (relative to CWD) |
| `LENGUA_DAILY_NEW_LIMIT` | `10` | Default cap on brand-new cards in a review batch (the per-user `daily_new_limit` setting overrides it) |
| `LENGUA_DAILY_TOTAL_LIMIT` | `50` | Default cap on total cards in a review batch (the per-user `daily_total_limit` setting overrides it) |
