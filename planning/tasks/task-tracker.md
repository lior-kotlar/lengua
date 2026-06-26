# Lengua Productionization — Master Task Tracker

This is the **master index** for the Lengua productionization plan (Streamlit → FastAPI +
React + Supabase + Cloud Run, packaged to iOS/Android via Capacitor). The granular,
PR-sized tasks live in the sibling `phase-N-*.md` files in this directory; you tick the
`- [ ]` checkboxes **there**, and this file rolls them up into a single phase-level view —
a summary table, the dependency graph and critical path, the cross-cutting workstreams,
setup readiness, and the launch milestones. Start here to orient, then open the relevant
phase file to do the work.

---

## How to use this tracker

- **Work phases in dependency order.** Honor the `Depends on` column and the dependency
  graph below — a phase isn't startable until its prerequisites are met.
- **Within a phase, the groups are mostly parallel.** Each phase file is split into
  numbered groups (e.g. `1.1`, `1.2`); unless a task lists an explicit `depends:`, groups
  can progress in parallel.
- **Each `- [ ]` is one PR-sized, independently verifiable task.** Every task carries a
  `verify:` line — the concrete check that proves it's done.
- **Tick a box only when its `verify` passes** and the PR lands green under the per-PR
  quality gate (100% green + ≥80% backend & frontend coverage + Playwright E2E).
- **Optionally promote a task to a GitHub issue when you start it** (and link the PR), so
  in-flight work is visible. Update the phase Status here as a phase moves.

## Status legend

`[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase summary

| Phase | File | Focus | Effort | Depends on | Tasks | Status |
|------:|------|-------|:------:|------------|:-----:|--------|
| 0 | [phase-0-foundations.md](phase-0-foundations.md) | Monorepo, tooling, CI quality gate, accounts | S–M | — | 45 | **impl complete** — 0.1–0.5 (CI gate 0.5.1–0.5.10), 0.6.1–0.6.2, 0.7.1–0.7.6/0.7.9/0.7.10/0.7.11, 0.8.x all merged green; gate live + green on `main`. Remaining = OWNER-only (non-blocking): 0.6.3/0.6.4 deferred to launch, 0.7.7/0.7.8 open. Does not block Phase 1. |
| 1 | [phase-1-backend-core.md](phase-1-backend-core.md) | FastAPI + Postgres core loop, LLM seam, OpenAPI | L | 0 | 34 | **impl complete** — all 34 tasks merged green + every exit-gate item verified. 1.1 done (lengua_core ported to a pure core: scheduler/proficiency/cards/config; SQLite relocated to legacy_streamlit/store; legacy app still runnable). 1.2 done (LLM provider seam: Groq default + Gemini reserved behind one Protocol, `get_provider()` fail-fast, shared retry/backoff + request caps; flip via `LLM_PROVIDER`). 1.3 done — 1.3a (async SQLAlchemy 2.0 engine/sessionmaker + `get_db` in `app/db/`, typed ORM models for all 8 tables matching the canonical schema, async `db_session` fixture) + 1.3b (`app/repositories/` = the only DB-touching layer, every method `user_id`-scoped; `app/services/` orchestrates pure `lengua_core` + repos with zero raw SQL — Generate→Save / Review-grade / Discover / languages / proficiency / settings). 1.4 done — Alembic at `apps/api/migrations/` (async `env.py` → `Base.metadata`, URL from `DATABASE_URL`); first migration = the full schema (6 app tables + `llm_usage`/`llm_budget`, applyable on bare Postgres, `alembic check` clean, upgrade↔downgrade round-trip); idempotent fixed-UUID dev-user seed (`scripts/seed_dev_user.py`, bare-DB insert + Supabase auth-backed). 1.5 in progress — 1.5a done (FastAPI app + `app/deps.py` `get_db`/`current_user`(seeded dev UUID)/`get_llm_provider`; core-loop routers wired into `create_app`: `GET/POST/PATCH/DELETE /languages`, `POST /generate`, `POST /cards/save`, `GET /review/due` split + `POST /review/{id}/grade`; Pydantic DTOs in `app/schemas/`; routers→services→repositories, domain errors→HTTP codes; in-process ASGI integration tests) + 1.5b done (remaining routers complete the full HTTP loop: `POST /discover` + `/discover/accept`, `POST /explain` caching into the `cards.word_explanations` JSONB column keyed by bare word—provider hit once, `GET/PUT /proficiency/{id}`, `GET/PUT /settings`; `tests/api/test_full_loop.py` walks Generate→Save→Review→grade→Discover over HTTP with a future `due`). 1.5 done. 1.6 done — `scripts/dump_openapi.py` dumps the canonical public schema (test-only routes excluded) to a checked-in `apps/api/openapi.json`, with `tests/test_openapi_stable.py` failing on drift vs `app.openapi()`; new `packages/api-types` pnpm-workspace package generates typed models + an `openapi-fetch` client from it (`apps/web` is now a workspace member on a single root `pnpm-lock.yaml`), and the `lint + format + types` CI job regenerates + drift-checks + typechecks it. 1.7 done — observability skeleton in `app/observability.py` (wired from `create_app()`): OpenTelemetry `TracerProvider` + auto-instrumentation for FastAPI/SQLAlchemy/httpx with a no-op exporter unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set, plus a `RequestLoggingMiddleware` emitting one structured JSON access line per request (`method`/`path`/`status`/`latency_ms`) stamped with the active `trace_id` for log↔trace correlation (OTel deps shipped as prod deps so the Docker image is instrumented too). **Phase 1 exit gate: all 7 items ✅** (full HTTP loop, reversible Alembic schema, `lengua_core` purity + SQL-only-in-repositories, LLM config-flip, OpenAPI→TS-client no-drift, observability hooks live). M1 reached. |
| 2 | [phase-2-auth-multitenancy.md](phase-2-auth-multitenancy.md) | Supabase Auth, per-user scoping, RLS, account lifecycle | M | 1 | 28 | **in progress** — 2.3 done (backend JWT verification): `app/auth.py` verifies the Supabase access token (signature + `exp` + `aud`; HS256 secret or RS256/ES256 via JWKS) → typed `CurrentUser`; `app/deps.get_current_user` (401 on missing/invalid) + back-compat `current_user`→UUID, exercised by a JWT-protected `GET /me`; expired/forged/`alg:none` all rejected; strict CORS allowlist (`CORS_ALLOW_ORIGINS`). Ships a reusable test auth helper (`tests/auth_helpers.py`: mint Supabase-shaped JWTs + `authenticate_as`/`install_test_auth` overrides) for the rest of Phase 2. 2.4 done (per-user scoping): the Phase 1.3b repositories/services already thread `current_user.id` with no hard-coded id (the `grep` half of 2.4.1 is clean) — added `tests/test_repositories_scoping.py` (per-method scoping), `tests/test_routes_auth.py` (every non-`/health` route → 401 without a JWT; `/health` → 200), `tests/test_cross_tenant_app.py` (user B can neither read nor mutate user A over the real stack, via a new `multiuser_client` real-JWT fixture), and an expanded `GET /me` (identity + `plan` + per-language proficiency via new `MeService`/`ProfilesRepository`, scoped to the token's user) with `tests/test_me.py`; `openapi.json` + `packages/api-types` regenerated. 2.5 done (profiles & demo account): new Alembic revision `0002` reproduces the canonical `handle_new_user()` + `on_auth_user_created` trigger (profiles-on-first-login, `plan='free'`), guarded so `alembic upgrade head` still applies on a bare Postgres; `tests/test_profiles_bootstrap.py` proves the trigger bootstraps exactly one free profile per signup (Alembic-built + live, no duplicate on re-login). `tests/test_no_guest.py` asserts no anon token issuance (`enable_anonymous_sign_ins=false` in the repo-root `supabase/config.toml`) + every write route is 401 without a JWT + zero anon inserts. `tests/test_demo_seed.py` exercises the existing `scripts/seed_e2e.py` demo/reviewer account end-to-end: email-verified, seeded rows, and a **real password-grant login → `GET /review/due`** (genuine ES256/JWKS token) returning ≥1 due card. 2.1.1/2.1.4/2.2.3 done (Supabase Auth config): the canonical repo-root `supabase/config.toml` now requires email confirmation (`enable_confirmations=true`) with a password policy (`minimum_password_length=8` + `lower_upper_letters_digits`), a full `site_url`+`additional_redirect_urls` allow-list (local/staging/prod web + `capacitor://localhost` + the `app.lengua://` deep-link scheme), and branded `[auth.email.template.*]` HTML emails under `supabase/templates/` (confirm/recovery/magic-link); `tests/test_auth_config.py` asserts the config contents (unit) + the live signup-confirmation / redirect-allow-list / branded-delivered-email behavior (integration). Google OAuth is scaffolded-enabled (env-wired, inert until creds) + Apple scaffolded-disabled, both documented in `infra/supabase/oauth-setup.md`. 2.6 done (RLS — defense-in-depth; merged after a 3-lens adversarial review + grant-coverage hardening): new Alembic revision `0003` reproduces the canonical RLS (enable RLS + an owner policy on the seven user tables, `llm_budget` left global), guarded on `auth.uid()` so it no-ops on a bare Postgres; new `app/db/rls.py` makes each request's DB session assume the non-privileged `authenticated` role + set `request.jwt.claims` (re-applied per transaction via an `after_begin` listener), wired through `app/deps.get_db` (now `Depends(current_user)`) so RLS is actually enforced beneath the app-layer scoping while migrations/seeds keep their privileged connections; `tests/test_rls_session.py` / `test_rls.py` / `test_rls_coverage.py` / `db/test_rls_migration.py` prove per-session scoping, DB-level cross-tenant isolation (incl. forged-row rejection + superuser survival), RLS-on-every-`user_id`-table coverage, and the migration round-trip. Full backend gate green (334 tests, 100% cov; `app/db/rls.py` 100% line+branch). The 3-lens review found one medium gap — the real `authenticated`-role write path was exercised end-to-end only for `/languages` — closed before merge by a full real-RLS write round-trip (`/cards/save` + `/review/grade` + `/proficiency`/`/settings` upserts through the un-overridden `get_db`) and an explicit grant-coverage check (`has_table_privilege`/`has_sequence_privilege` on all 7 RLS tables + the 3 identity sequences). 2.7 done (historical data migration): `scripts/import_sqlite.py` imports the operator's legacy single-user `data/lengua.db` into the multi-tenant Postgres schema under one CLI-passed account UUID via a privileged (`postgres`) connection (RLS-exempt) — remapping old integer ids to the new identity ids parent→child, preserving `fsrs_state`/`due`/`saved`/proficiency scores, folding legacy `settings`→`user_settings`; idempotent via per-table natural keys with a `--dry-run` that rolls the whole import back (`tests/test_import_sqlite.py`, 7 tests: source-count match + card spot-check, dry-run writes nothing, double-import no duplicates); runbook + README documented. 2.8 done (account-lifecycle export + delete) — **3-lens adversarial review → approve; hardened then merged** (security-sensitive + destructive): new `app/routers/account.py` adds `GET /account/export` (a downloadable `AccountExport` JSON bundle — profile/languages/cards/reviews/proficiency/settings — assembled by `ExportService` via repository-only reads, scoped to `current_user`) and `DELETE /account` (hard-delete via `AccountDeletionService` calling the Supabase Auth Admin API with the service-role key; the `auth.users → profiles → domain` `on delete cascade` removes everything atomically — the single irreversible step runs last, so a failure deletes nothing → `502` retryable). 2.8.2 confirmed the cascade already exists in both the canonical + live Alembic schema (no migration); the dependent table is `llm_usage`. Cross-tenant guard is structural (no user-id parameter; id derived from the JWT). Backend gate green (366 tests, ~99.9% cov; the new account router/service/schema 100%), incl. live integration proof (real A+B users: A's `DELETE /account` removes A's auth row + all domain rows, B untouched, A's old token rejected by GoTrue) + a live double-`DELETE` idempotency test (both calls 204) + literal `curl /account/export` scoping. Post-review hardening: the Admin delete sends `should_soft_delete=false` **explicitly** so the cascade-firing hard delete can't be flipped by a GoTrue default; the RLS-bypassing service-role key is typed `pydantic.SecretStr` (masked in logs/reprs); runbook records the "never migrate prod Alembic-only" cascade invariant. `openapi.json` + `packages/api-types` regenerated. Remaining: 2.1.2/2.1.3 (owner Google/Apple OAuth creds) + 2.2.1/2.2.2 (owner Resend SMTP + SPF/DKIM/DMARC). |
| 3 | [phase-3-llm-quota.md](phase-3-llm-quota.md) | LLM quota, rate-limit, cost-guard kill-switch | M | 2 | 26 | not started |
| 4 | [phase-4-web-app.md](phase-4-web-app.md) | React web app (parity with Streamlit) | L | 1–3 | 44 | not started |
| 5 | [phase-5-observability.md](phase-5-observability.md) | Tracing, logs, metrics, dashboards, alerts | S–M | 1 (starts), 3, 6 | 32 | not started |
| 6 | [phase-6-infra-cicd.md](phase-6-infra-cicd.md) | Environments, CI gate, CD pipeline, rollback | M | 1, 2 | 48 | not started |
| 7 | [phase-7-mobile.md](phase-7-mobile.md) | Capacitor → signed iOS + Android, OTA | M | 4, 6 | 50 | not started |
| 8 | [phase-8-compliance-store.md](phase-8-compliance-store.md) | Privacy/GDPR, store labels, listings, closed tests | M | 7 | 27 | not started |
| 9 | [phase-9-launch.md](phase-9-launch.md) | Coordinated web + iOS + Android launch + 48h watch | S | 0–8 | 15 | not started |

**Total: 349 PR-sized tasks across 10 phases.**

---

## Dependency graph & critical path

```
            ┌──────────────────────── cross-cutting ────────────────────────┐
            │  Observability (P5): instrument from P1 ──► finish in P5       │
            │  Infra/CI (P6): CI gate from P0 ──► deploy pipeline in P6      │
            └───────────────────────────────────────────────────────────────┘

  0 ──► 1 ──► 2 ──► 3 ──► 4 (web) ──► 7 (mobile) ──► 8 (compliance) ──► 9 (launch)
        │         │      │             ▲                  ╲                 ▲
        │         │      │             │                   ╲                │
        │         │      │             └── 6 (infra/CI) ────┘  8 overlaps 7 │
        │         │      │                  runs alongside 4–6              │
        │         │      └────────────────────────────────────────────────┐│
        │         └── 5 (observability) starts here, runs alongside 1–6 ───┘│
        │                                                                    │
        └── 9 needs web (P4) + iOS + Android (P7, via P8) all green ─────────┘
```

Edges in words:

- **0 → 1 → 2 → 3** — the backend spine (foundations, core loop, auth/multi-tenancy, cost guard).
- **4 (web)** follows **3**; **7 (mobile)** wraps the **4** web build; **8 (compliance)**
  overlaps **7**; **9 (launch)** needs **web + iOS + Android** all ready.
- **5 (observability)** *starts* in Phase 1 (auto-instrument as the backend is built) and
  runs alongside **1–6**; a couple of its tasks (infra dashboard, external uptime) land
  after the matching **6** deploy.
- **6 (infra/CI)** runs alongside **4–6** (CI gate already seeded in Phase 0).

**Critical path (explicit):**

```
0 → 1 → 2 → 3 → 4 → 7 → 8 → 9
```

---

## Cross-cutting workstreams

These run *across* phases rather than as a single block — track them continuously.

- **Observability** — instrument from **P1** (OTel auto-instrumentation + structured logs
  wired as the backend is built; custom quota spans land with **P3**), then *finish* in
  **P5** (dashboards, alerts, Sentry, external uptime). See
  [phase-5-observability.md](phase-5-observability.md).
- **Infra / CI** — the blocking **CI gate is seeded in P0** (`phase-0` group 0.5) and the
  full **deploy pipeline (CD) lands in P6** (build → Cloud Run staging → gated prod →
  rollback). See [phase-6-infra-cicd.md](phase-6-infra-cicd.md).
- **Testing & quality gate** — applies to **every PR in every phase**: 100% green + ≥80%
  backend & frontend coverage + Playwright E2E with the LLM stubbed. A task is not done
  until its tests keep coverage ≥80%. See [../09-testing-quality.md](../09-testing-quality.md).
- **Security & compliance** — threaded through **P2** (JWT/RLS/CORS, account
  export+delete), **P3** (shared-key abuse guard), **P7** (signing material as secrets,
  no leaked keys), and **P8** (privacy policy, GDPR consent/residency, store data-safety,
  deletion cascade). See [../07-security-compliance.md](../07-security-compliance.md).

---

## Setup readiness (pre-implementation)

A readiness validation on **2026-06-25** verified **~47 account/infra items done** (GitHub
repo + 28 Actions secrets, both Supabase projects, GCP `lengua-prod` + Artifact Registry +
`github-ci` SA, Vercel project, Groq/Gemini/Resend/Grafana/Sentry keys as CI secrets,
Ben's local `.env`/gcloud/Docker). Owner (Kotlar) item status (updated 2026-06-25):

1. Branch protection on `main` — **DEFERRED to launch** (non-blocking; would break the
   autonomous self-merge flow if enabled now). See [owner-deferred-tasks.md](owner-deferred-tasks.md).
2. Dependabot vulnerability alerts + automated security fixes — **DEFERRED to launch**
   (non-blocking). See [owner-deferred-tasks.md](owner-deferred-tasks.md).
3. Two CI secrets (`GCP_REGION`, `SENTRY_ORG`) — **still outstanding** (needed in Phase 5/6, not
   Phase 0).
4. Vercel access for Ben — **RESOLVED**: free-tier single manager seat; Ben is the account
   holder/manager for `lengua`. Non-blocking.
5. Resend custom-SMTP delivery confirmed in both Supabase projects — **still outstanding**
   (needed for Phase 2 auth emails).
6. Grafana Cloud + Sentry access for Ben — **DONE 2026-06-25** (Ben joined both).

So only items **3** (deploy/observability secrets) and **5** (auth email) remain truly open, and
**1–2** are deferred-by-design to launch — see [owner-deferred-tasks.md](owner-deferred-tasks.md).
**None of these block writing code.** **Paid store accounts** (Apple Developer $99/yr, Google
Play $25 one-time) are **deferred to Phase 7** and are not part of Phase 0.

---

## Milestones

| Milestone | What it proves | Lands at |
|-----------|----------------|----------|
| **M1** | Backend Generate→Save→Review→Discover loop runs over HTTP | end of **P1** |
| **M2** | Multi-user (auth + RLS) with the LLM cost guard armed | end of **P3** |
| **M3** | React web app at full parity with the legacy Streamlit app | end of **P4** |
| **M4** | Deployed to staging **and** prod (auto-staging + gated prod) | end of **P6** |
| **M5** | Signed iOS + Android builds installable on real devices | end of **P7** |
| **M6** | Coordinated web + iOS + Android launch (v1 live) | **P9** |
