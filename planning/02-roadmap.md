# 02 — Roadmap (phased task plan)

Phases are ordered by dependency, not date. Effort tags: **S** ≈ a day or two, **M** ≈ about a
week, **L** ≈ multiple weeks (solo, part-time — adjust to your pace).

Because we launch **all platforms together**, the web app is built first (Capacitor wraps it)
and the **launch gate (Phase 9) requires web + iOS + Android ready at once**. Phases 5
(observability) and 6 (infra) run partly in parallel with feature work — instrument and
deploy continuously rather than at the end.

Legend: `[ ]` todo. Treat each checkbox as a task; promote to issues when you start.

> **Quality gate applies to every phase.** From Phase 0 on, all work lands via PRs that pass
> the blocking gate in [09-testing-quality.md](09-testing-quality.md): 100% tests pass + ≥80%
> coverage (backend & frontend) + Playwright E2E. "Done" for any feature task below includes
> the tests that keep coverage ≥80% — it is not a separate phase.

---

## Phase 0 — Foundations & accounts · **S–M**

Goal: repo, tooling, and all free-tier accounts ready.

- [ ] Restructure to the monorepo layout in [01-architecture.md](01-architecture.md)
      (`apps/api`, `apps/web`, `packages/`, `infra/`); keep legacy Streamlit runnable.
- [ ] Decide package manager / tooling: `uv` or `pip-tools` (api), `pnpm` (web).
- [ ] Create accounts: **GitHub**, **Supabase**, **Google Cloud** (Cloud Run), **Vercel**,
      **Grafana Cloud**, **Sentry**, **Groq** (free-tier key — the default LLM provider, needed
      now). **Google AI Studio** (Gemini key) can wait — only needed when you flip to Gemini later.
- [ ] Pay + register the unavoidable store accounts: **Apple Developer ($99/yr)**,
      **Google Play ($25 one-time)**. (Start early — Apple identity verification can take days.)
- [ ] Set up the Supabase CLI local stack (Docker) for the `local` env.
- [ ] Add base tooling: ruff + mypy + pytest + pytest-cov (api); eslint + prettier + tsc +
      vitest + Playwright (web); pre-commit hooks; a `make verify` / `pnpm verify` local gate.
- [ ] Stand up the **per-PR quality gate** ([09](09-testing-quality.md)): lint + types +
      backend/frontend tests with **80% coverage thresholds** + a first Playwright smoke on an
      ephemeral stack (Gemini stubbed) + security scans. Make all of it pass on a trivial PR.
- [ ] Enable **branch protection** on `main` (required status checks, up-to-date, review) and
      add `.github/pull_request_template.md` encoding the Definition of Done.
- [ ] Build shared test infra early: fixtures/factories, the **deterministic Gemini fake**,
      and a test Postgres (Supabase CLI / testcontainers).
- [ ] Create `docs/` with placeholder `privacy-policy.md` and `runbook.md`.

**Done when:** `apps/api` and `apps/web` build/run empty; CI is green on a PR; all accounts exist.

---

## Phase 1 — Backend core (FastAPI + Postgres, no auth yet) · **M–L**

Goal: the domain logic runs behind FastAPI against Postgres, single hard-coded test user.

- [ ] Move `lengua/*` into `apps/api/lengua_core/` unchanged where possible.
- [ ] Replace the SQLite layer with a Postgres persistence layer (SQLAlchemy 2.x or
      SQLModel); introduce a repository/service boundary so core logic stays DB-agnostic.
- [ ] Author the **multi-tenant Postgres schema** (see [03-backend.md](03-backend.md)) — even
      before auth, build it with `user_id` columns and a seeded dev user.
- [ ] Set up **Alembic** migrations; first migration = full schema.
- [ ] FastAPI routers for the core loop: `languages`, `generate`, `cards`, `review`,
      `discover`, `explain`, `proficiency`, `settings` (see endpoint list in 03).
- [ ] Port LLM calls behind an async-friendly **provider interface** (`LLM_PROVIDER`, **default
      `groq`**): a `groq` impl (OpenAI-compatible + JSON parse into `GeneratedCard`/`WordNote`)
      and the existing `gemini` impl; keep retry/backoff. **All dev/test/CI runs on Groq's free
      tier**; the `gemini` impl exists so flipping the env var later is a no-code switch.
- [ ] Unit tests for scheduler/proficiency (pure logic) + a few API integration tests
      against a throwaway Postgres (testcontainers or local Supabase).
- [ ] Generate the **OpenAPI schema**; wire `packages/api-types` codegen.

**Done when:** full Generate→Save→Review→Discover loop works via HTTP for one seeded user.

---

## Phase 2 — Auth & multi-tenancy · **M**

Goal: real accounts; every row owned and isolated.

- [ ] Configure Supabase Auth: email/password + email verification, Google OAuth, Apple OAuth
      (Apple sign-in is required on iOS if Google is offered — see 07).
- [ ] Wire a **custom SMTP** provider (Resend/Brevo free tier) for verification/reset emails
      with SPF/DKIM — the built-in Supabase sender is dev-only.
- [ ] FastAPI JWT verification dependency (Supabase JWT secret/JWKS) → `current_user`.
- [ ] Replace the seeded user with `current_user`; scope **all** queries by `user_id`.
- [ ] Add a `profiles` row on first login (trigger or app-side upsert), with `plan='free'`
      (paid-ready; no billing in v1).
- [ ] **Signup required** (no guest mode); seed a **demo/reviewer account** that exercises the
      full loop for store review.
- [ ] Enable **RLS policies** (`user_id = auth.uid()`) on all user tables.
- [ ] Write a **data-migration script** to import your existing local `data/lengua.db` into
      your new prod account (languages, cards, reviews, proficiency).
- [ ] Account lifecycle endpoints: data export (JSON) + **account deletion** (hard delete,
      cascade) — needed for store compliance.

**Done when:** two users cannot see each other's data (verified via tests + RLS), and your
historical data is importable.

---

## Phase 3 — LLM quota, rate-limiting & cost guard · **S–M**

Goal: the operator-funded key can never produce a bill. The gate is provider-agnostic — same
checks whether the active provider is Groq (default, now) or Gemini (later); ceilings come from
the active provider's free-tier limits.

- [ ] `gemini_usage` table + per-user **daily caps** (generate / discover / explain), with
      values from per-user settings, bounded by hard server maximums.
- [ ] Per-user **rate limiting** (sliding window; `slowapi` or Postgres/Upstash counters).
- [ ] **Global daily budget kill-switch**: project-wide counter; when near the Gemini free
      daily limit, generation returns a friendly "daily limit reached, try tomorrow."
- [ ] Concurrency limit + exponential backoff honoring Gemini 429s.
- [ ] Cost minimization: cap words/request and output tokens; cache `word_explanations`
      (already persisted); reuse Discover results.
- [ ] Require **verified email** before any Gemini call; basic signup abuse guard.
- [ ] Metrics + spans for every Gemini call (model, latency, tokens, cap-hit, budget-left).
- [ ] **Design a BYOK seam (don't build it yet):** make key resolution pluggable so a
      user-supplied Gemini key could later override the operator key. This is the growth escape
      hatch for the "small public, slow growth" scale — if signups outpace the free tier, you
      flip on BYOK instead of paying or rewriting (see [08](08-open-questions-and-costs.md)).

**Done when:** load test shows caps/limits enforced and the global guard trips correctly
without any paid usage.

---

## Phase 4 — React web app (parity with Streamlit) · **L**

Goal: a usable website covering the whole product.

- [ ] App shell: React + TS + Vite, react-router, **TanStack Query**, supabase-js, a
      component library + theming.
- [ ] Auth screens: sign up / log in / verify / reset / OAuth buttons; session handling +
      token refresh + 401 retry.
- [ ] Screens (port from `pages/`): **Generate**, **Review** (reveal + Again/Hard/Good/Easy
      with the existing colors), **Discover**, **Settings**, plus **Language management** and
      **Account** (export/delete).
- [ ] **RTL + diacritics**: `dir=rtl` per language, correct fonts/shaping for Arabic/Hebrew,
      vowel-marks toggle; **tap-a-word** interaction.
- [ ] Sidebar/level UI: CEFR band + progress + manual override.
- [ ] Typed API client from `packages/api-types`.
- [ ] Loading/error/empty states; friendly handling of 429 (quota) responses.
- [ ] Web E2E smoke tests (Playwright) for the core loop.

**Done when:** a browser user can do everything the Streamlit app did, signed in, against the API.

---

## Phase 5 — Observability · **S–M** (start in Phase 1, finish here)

Goal: see what's happening in prod.

- [ ] OpenTelemetry in FastAPI: auto-instrument HTTP, SQLAlchemy, httpx; OTLP → Grafana Cloud.
- [ ] Custom spans/metrics: Gemini calls, FSRS reviews, signups, quota hits, budget remaining.
- [ ] **Structured JSON logs** correlated with `trace_id`.
- [ ] **Sentry** for backend + web + (later) mobile.
- [ ] **Product analytics**: PostHog (free, EU-hosted, anonymized, **consent-gated**) — the
      activation funnel (signup → generate → review) + retention. Distinct from OTel/Sentry.
- [ ] Dashboards (RED metrics, Gemini usage vs budget, daily reviews, errors); **alerts**
      (error rate, latency, budget≈exhausted, uptime) to email/Slack/Discord.
- [ ] Uptime checks (UptimeRobot/Grafana synthetic) on prod health endpoint.

**Done when:** a trace spans client→API→DB/Gemini, logs are correlated, and a test alert fires.

---

## Phase 6 — Infra, environments & CI/CD · **M** (overlaps 4–5)

Goal: three environments and automated deploys.

- [ ] Dockerize the API; deploy to **Cloud Run** (staging + prod services).
- [ ] **Vercel** projects for web (staging + prod) from the same repo.
- [ ] Two Supabase hosted projects (staging, prod); manage schema via Alembic + Supabase CLI;
      seed scripts.
- [ ] Secrets per platform (Cloud Run secrets, Vercel env, GitHub Actions secrets) — Gemini
      key, Supabase keys/JWT secret, OTLP creds, Sentry DSN.
- [ ] CI/CD pipelines: PR = lint/test; merge to `main` = deploy **staging** + run migrations;
      tag/release (or manual approval) = deploy **prod**.
- [ ] Health checks, readiness, and rollback procedure documented in `docs/runbook.md`.
- [ ] (Optional) custom domain or free subdomains for web + API.

**Done when:** merging to `main` ships staging automatically; prod is a one-click gated promote.

---

## Phase 7 — Mobile packaging (Capacitor → iOS + Android) · **M**

Goal: the web app installable from both stores.

- [ ] Add Capacitor to `apps/web`; generate `ios/` and `android/` projects.
- [ ] Native config: app id, name, **icons + splash screens**, status bar, deep links,
      permissions; point the app at the prod API.
- [ ] Native plugins: **Local Notifications** — schedule a **daily review reminder** when cards
      are due (permission prompt + scheduling), offline, no server; Preferences/secure storage
      (tokens), Network (offline detection), App (deep links).
- [ ] Make auth work in the native webview (OAuth redirect handling for Google/Apple).
- [ ] **Signing**: iOS certificates/provisioning profile; Android keystore — store as CI
      secrets; consider **Fastlane** to automate build + upload.
- [ ] Integrate **OTA live updates** (e.g. Capgo, OSS/free) with per-environment channels so
      web-layer fixes ship without store review; keep native changes on the store track.
- [ ] Build + run on real devices; fix mobile-specific layout/RTL/keyboard issues.

**Done when:** signed iOS and Android builds install and run the full loop against prod.

---

## Phase 8 — Compliance & store readiness · **S–M** (overlaps 7)

Goal: clear store review.

- [ ] Publish a **privacy policy** (must disclose Supabase + that vocab/sentences go to
      Google's Gemini API) and a support/contact URL.
- [ ] GDPR for the EU audience: **analytics consent** banner, **EU data residency**, and the
      export/delete flows surfaced in-app.
- [ ] **Account deletion** reachable in-app (Apple requires it; Play requires a deletion path
      + a web request form).
- [ ] Apple **privacy nutrition labels** + Google Play **Data Safety** form.
- [ ] Age rating questionnaires; export-compliance (encryption) declaration.
- [ ] Store listings: name, descriptions, **screenshots** (web + each device size), keywords.
- [ ] TestFlight (iOS) + Play **internal testing** track; run a closed test.

**Done when:** both store listings are complete and a test build passes internal review.

---

## Phase 9 — Launch (all platforms together) · **S**

- [ ] Final prod smoke test across web + iOS + Android.
- [ ] Submit iOS for App Store review; promote Android to production.
- [ ] Deploy web to prod domain.
- [ ] Watch dashboards/alerts for the first 48h; keep a rollback ready.

**Done when:** all three are live and the success criteria in [00-overview.md](00-overview.md)
are met.

---

## Post-launch backlog (not blocking v1)

Offline review + sync · server push notifications (FCM/APNs) · product analytics (PostHog
free) · TTS audio for sentences · streaks/gamification · shared/importable decks · richer
import/export · i18n of the UI itself. Tracked in
[08-open-questions-and-costs.md](08-open-questions-and-costs.md).

## Critical path & parallelism

```
0 ─► 1 ─► 2 ─► 3 ─┐
            └─► 4 (web) ──────────────► 7 (mobile) ─► 8 ─► 9 (launch)
5 (observability) runs alongside 1–6
6 (infra/CI) runs alongside 4–5
```
Web (4) must precede mobile (7) because Capacitor wraps the web build. Observability (5) and
infra (6) are continuous, not a final step.
