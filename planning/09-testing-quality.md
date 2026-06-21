# 09 — Testing & Quality Gates (per-PR pipeline)

Every change lands through a Pull Request that must pass a **blocking** quality gate before it
can merge. No direct pushes to `main`.

## The gate (decision: strictest option)

A PR is mergeable only when **all** of these are green:

| Check | Requirement | Tool |
| --- | --- | --- |
| **Tests pass** | **100%** of tests pass — no failures, no silent skips | pytest, vitest, Playwright |
| **Backend coverage** | **≥ 80%** (line + branch) | pytest + `pytest-cov` (`--cov-fail-under=80`) |
| **Frontend coverage** | **≥ 80%** | vitest (`coverage.thresholds` 80, v8 provider) |
| **E2E** | Playwright critical-journey suite passes | Playwright on an ephemeral stack |
| **Lint** | clean | ruff (api), eslint (web) |
| **Format** | clean | ruff format / prettier (check mode) |
| **Types** | clean | mypy (api), tsc `--noEmit` (web) |
| **Build** | API image + web bundle build | Docker / Vite |
| **Security** | no new criticals, no secrets | pip-audit, npm/pnpm audit, gitleaks |
| **A11y + perf** | budgets met (start advisory, then blocking) | axe, Lighthouse CI |

> Coverage and "tests pass" are enforced **separately for backend and frontend** — each must
> independently hit 80% and 100%-pass.

## Branching & PR workflow

- **Trunk-based**: short-lived branches off `main`; open a PR; never push to `main` directly.
- **Branch protection on `main`**: require the status checks above, require the branch be
  up-to-date, require ≥1 approving review (self-review is fine while solo), and **dismiss stale
  approvals** on new commits.
- **Squash merge** with a Conventional-Commits title (`feat:`, `fix:`, `chore:` …) so a
  changelog can be generated later.
- Merge to `main` → auto-deploy **staging** + run migrations (see
  [05-infra-deploy.md](05-infra-deploy.md)); prod is a separate gated promotion.

## Test pyramid — what to test where

- **Unit (the bulk, fast, no I/O):** pure logic — FSRS scheduling (`scheduler`), proficiency
  math (`proficiency`), prompt assembly (`prompts`), quota/cap calculations, Pydantic schema
  validation. These are where 80% is cheap and valuable.
- **Integration (real Postgres):** repositories/services against local Supabase or
  testcontainers — CRUD, **auth + RLS cross-tenant isolation**, the **quota gates + global
  budget kill-switch**, and that **Alembic migrations apply cleanly** (and round-trip).
- **Contract:** the **OpenAPI schema is stable** and the generated TS client in
  `packages/api-types` matches the server (a drift test fails the PR).
- **E2E (Playwright, web):** critical journeys — sign up / log in, generate → save, review +
  grade (all four ratings), discover, settings, **account deletion**, and the **429 "daily
  limit reached"** path. Mobile-webview E2E (Appium/Maestro) is a post-launch addition.
- **Non-functional:** a small **load test** for the quota/budget path (Phase 3); Lighthouse
  perf budget + axe accessibility on the web build.

## Coverage policy (make the number meaningful)

- **Exclusions** (configured, not hand-waved): generated code (`packages/api-types`), Alembic
  migrations, `__main__`/config/settings boilerplate, type-only files, test files, and native
  scaffolding (`ios/`, `android/`).
- **Ratchet:** overall coverage may **never drop** below 80% — and ideally never below its
  current value. The diff itself should also be ≥80% covered (a PR can't add untested code and
  hide behind a high baseline).
- Post a **coverage delta comment** on each PR for visibility.

## E2E on every PR — keeping it fast and non-flaky

You chose to require E2E on every PR. To keep that practical:

- **Ephemeral stack per PR:** build the web bundle + API container + a disposable Postgres
  (local Supabase / testcontainers) seeded with fixtures; run Playwright headless against it.
- **Stub the LLM provider deterministically** in E2E (a fake `llm` impl that returns canned
  cards/explanations — provider-agnostic, so it stands in for Groq or Gemini). This (a) never
  burns real quota, (b) removes model nondeterminism, (c) lets us assert *app* behavior, not the
  model's wording. Keep **one** separate, **non-blocking, scheduled** smoke run that hits the
  real provider (Groq now) to catch API/contract drift.
- **Prompt-quality validation on Gemini (later):** because the provider is a flip of
  `LLM_PROVIDER`, eyeballing real Gemini output is a config change, not a code change. When you
  want to check prompts against the prod model, run the manual smoke with `LLM_PROVIDER=gemini`;
  not part of the per-PR gate.
- **Small required set on PR** (critical-path smoke); run the **full/long E2E nightly**.
- **Flaky policy:** auto-retry a failing E2E once; if it still fails it **blocks**. Chronically
  flaky tests are **quarantined behind a tracked issue**, never silently skipped.
- **Parallelize/shard** Playwright and **cache** browsers + deps to keep wall-clock down.

## Per-PR pipeline (order)

```
PR opened / updated
  1. setup + restore caches (uv/pip, pnpm, Playwright browsers)
  2. lint + format check        (ruff, eslint, prettier)
  3. typecheck                  (mypy, tsc --noEmit)
  4. backend tests + coverage   (pytest --cov, fail < 80%)  ── unit + integration (Postgres)
  5. frontend tests + coverage  (vitest --coverage, fail < 80%)
  6. contract test              (OpenAPI ↔ generated client drift)
  7. build                      (API image, web bundle)
  8. E2E                        (ephemeral stack, Gemini stubbed) — must pass
  9. security                   (pip-audit, pnpm audit, gitleaks)
 10. a11y + perf budgets        (axe, Lighthouse CI)
  → all required checks green ⇒ mergeable
```

## Definition of Done (encode as the PR template)

`.github/pull_request_template.md` with a checklist:

- [ ] Tests added/updated; backend & frontend coverage stay **≥ 80%**; all checks green.
- [ ] Behavior change? **README updated** (per `CLAUDE.md` rule) and OpenAPI + TS types
      regenerated.
- [ ] New critical path is **observable** (spans/metrics/logs added — see
      [06-observability.md](06-observability.md)).
- [ ] **Security**: no secret in the client bundle; inputs validated; queries scoped to the
      authenticated user.
- [ ] Schema change includes a **backwards-compatible Alembic migration** (+ RLS policy).
- [ ] Quota-affecting change keeps the Gemini cost guard intact.

## Test infrastructure to build (tasks)

- [ ] Fixtures/factories for users, languages, cards, reviews (factory-boy or simple builders).
- [ ] A **deterministic Gemini fake** shared by unit/integration/E2E.
- [ ] Local Postgres for tests (Supabase CLI or testcontainers) wired into CI.
- [ ] E2E seed + a **reviewer/demo account** (reused for store review).
- [ ] One-command local gate: `make verify` (api) / `pnpm verify` (web) that runs the whole
      pipeline before pushing, so PRs rarely fail in CI.
- [ ] GitHub branch-protection config + required-checks list committed/documented.

## Tooling summary

| Area | Backend | Frontend / E2E |
| --- | --- | --- |
| Test runner | pytest | vitest / Playwright |
| Coverage | pytest-cov (branch) | vitest v8 coverage |
| Lint/format | ruff (+ ruff format) | eslint + prettier |
| Types | mypy | tsc |
| Security | pip-audit, gitleaks | pnpm audit, gitleaks |
| Perf/a11y | — | Lighthouse CI, axe |
| DB for tests | Supabase CLI / testcontainers | (shared in E2E stack) |
