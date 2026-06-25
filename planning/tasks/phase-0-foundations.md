# Phase 0 — Foundations & accounts

> **Effort:** S–M  ·  **Depends on:** nothing  ·  **Unlocks:** Phase 1
> **Source:** roadmap Phase 0 (../02-roadmap.md) · deep dive (../08-open-questions-and-costs.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** the monorepo layout, base tooling, the per-PR CI quality gate, branch protection, shared test infra, and all free-tier accounts are in place — `apps/api` and `apps/web` build/run empty, CI is green on a trivial PR, and every account exists.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 0.1 — Monorepo restructure  ·  M

_Context: lift the repo into the `apps/ packages/ infra/` shape from ../01-architecture.md while keeping the legacy Streamlit app runnable so we can dogfood without regressions._

- [x] **0.1.1** Create the top-level monorepo skeleton (`apps/api/`, `apps/web/`, `packages/`, `infra/`, `docs/`) with `.gitkeep`/README stubs; add a root `README.md` section describing the layout.
      verify: `test -d apps/api && test -d apps/web && test -d packages && test -d infra && test -d docs` exits 0; root README lists all four dirs.
- [x] **0.1.2** Move the existing `lengua/*` package under `apps/api/lengua_core/` and `pages/`, `app.py` to a clearly-marked legacy location, fixing imports so the Streamlit app still launches.
      verify: `streamlit run app.py` (or the relocated entrypoint) starts without ImportError and serves the home page locally.
      depends: 0.1.1
- [x] **0.1.3** Add a root `.gitignore`, `.editorconfig`, and a root `README.md` "Repo layout & how to run each app" section covering api, web, legacy Streamlit.
      verify: `git status` shows no stray build/venv/node_modules artifacts after a clean build; README renders the layout tree.
- [x] **0.1.4** Add a root `Makefile` (or `justfile`) with `make verify` that fans out to api + web verify targets, and document the one-command local gate in the README.
      verify: `make verify` runs api and web lint/type/test targets and exits 0 on the empty scaffolds.
      depends: 0.2.4, 0.3.5

## 0.2 — Backend tooling (apps/api)  ·  M

_Context: stand up the FastAPI service shell with `uv`, ruff, mypy, pytest, and pytest-cov so backend PRs have a real gate from day one. LLM provider defaults to Groq (`llama-3.1-8b-instant`) for all dev/CI._

- [x] **0.2.1** Initialize `apps/api` with `uv` + `pyproject.toml` (FastAPI, uvicorn, pydantic, httpx, pytest, pytest-cov, ruff, mypy as dev deps); pin Python version.
      verify: `uv sync` resolves and `uv run python -c "import fastapi"` exits 0.
- [x] **0.2.2** Add a minimal FastAPI app exposing `GET /health` returning `{"status":"ok"}` and run it under uvicorn.
      verify: `uv run uvicorn app.main:app` then `curl -s localhost:8000/health` returns 200 with `{"status":"ok"}`.
      depends: 0.2.1
- [x] **0.2.3** Configure ruff (lint + format) and mypy (strict-ish) with config in `pyproject.toml`; clean the scaffold.
      verify: `uv run ruff check . && uv run ruff format --check . && uv run mypy .` all exit 0.
      depends: 0.2.1
- [x] **0.2.4** Configure pytest + pytest-cov with `--cov-fail-under=80` and branch coverage; add a first test for `/health`. Add an `api` make/uv target `verify` that runs lint+format+types+tests.
      verify: `uv run pytest --cov --cov-branch` passes with coverage ≥80% on the scaffold; the verify target exits 0.
      depends: 0.2.2, 0.2.3
- [x] **0.2.5** Add a config/settings module reading env (incl. `LLM_PROVIDER` default `groq`, model `llama-3.1-8b-instant`) and a `.env.example` documenting required vars; exclude settings boilerplate from coverage.
      verify: app boots with only `.env.example` values copied to `.env`; `LLM_PROVIDER` defaults to `groq` when unset (asserted in a unit test).

## 0.3 — Frontend tooling (apps/web)  ·  M

_Context: stand up the React + TS + Vite web shell with pnpm, eslint, prettier, tsc, vitest, and Playwright. UI stack is Tailwind + shadcn/ui (decision round 5)._

- [x] **0.3.1** Initialize `apps/web` with `pnpm` + Vite (React + TS template); app renders a placeholder home route via react-router.
      verify: `pnpm install && pnpm build` succeeds and `pnpm dev` serves the placeholder page locally.
- [x] **0.3.2** Add Tailwind CSS + shadcn/ui base config and one sample shadcn component on the home route.
      verify: `pnpm build` succeeds; the home route renders the sample component with Tailwind classes applied (visible in `pnpm preview`).
      depends: 0.3.1
- [x] **0.3.3** Configure eslint + prettier + `tsc --noEmit` with shared config; clean the scaffold.
      verify: `pnpm lint && pnpm exec prettier --check . && pnpm exec tsc --noEmit` all exit 0.
      depends: 0.3.1
- [x] **0.3.4** Configure vitest with v8 coverage and 80% thresholds; add a first component/render test.
      verify: `pnpm test --coverage` passes with coverage ≥80% on the scaffold and fails if thresholds drop.
      depends: 0.3.1
- [x] **0.3.5** Add Playwright with a single smoke spec that loads the home page; add a `pnpm verify` script running lint+format+types+unit+build.
      verify: `pnpm exec playwright test` passes the home-page smoke headless; `pnpm verify` exits 0.
      depends: 0.3.3, 0.3.4

## 0.4 — Shared test infrastructure  ·  M

_Context: build the fixtures/factories, the deterministic LLM fake (provider-agnostic — stands in for Groq or Gemini), and a throwaway test Postgres so every later phase's tests are cheap and never burn real quota._

- [x] **0.4.1** Add backend fixtures/factories for users, languages, cards, reviews (factory-boy or simple builders) in `apps/api/tests`.
      verify: `uv run pytest tests/test_factories.py` builds each entity and asserts required fields are populated.
- [x] **0.4.2** Implement the deterministic LLM fake (`FakeLLM`) behind the provider interface returning canned `GeneratedCard`/`WordNote`; shared by unit/integration/E2E.
      verify: `uv run pytest tests/test_fake_llm.py` asserts identical structured output across repeated calls (no nondeterminism, no network).
- [x] **0.4.3** Wire a throwaway test Postgres (Supabase CLI stack or testcontainers) into the pytest session with a fixture that gives a clean DB per test module.
      verify: `supabase start` (or testcontainers spin-up) runs in CI and `uv run pytest tests/test_db_fixture.py` connects, creates a temp table, and tears down.
- [x] **0.4.4** Add an E2E seed script + a reviewer/demo account fixture the Playwright stack consumes (reused later for store review).
      verify: running the seed against a fresh test DB produces the demo account and a non-empty card set, asserted by a seed-verification test.
      depends: 0.4.1, 0.4.3

## 0.5 — Per-PR quality gate (CI)  ·  L

_Context: encode the blocking pipeline from ../09-testing-quality.md as GitHub Actions and prove it passes on a trivial PR. E2E runs on an ephemeral stack with the LLM stubbed (FakeLLM), so it never burns Groq/Gemini quota._

- [x] **0.5.1** Add a CI workflow job: setup + dependency/Playwright-browser caching for both uv and pnpm.
      verify: a PR run shows cache hits on the second run and the setup job goes green. ✓ run 28171555344 (setup green; second-run cache hits: `Cache hit for: setup-uv-…`, `node-cache-…-pnpm-…`, `playwright-Linux-1.61.1`).
- [x] **0.5.2** Add lint + format + typecheck jobs (ruff/eslint/prettier, mypy/tsc) as required checks.
      verify: a PR that introduces a lint error fails the job; the clean scaffold PR passes it. ✓ clean head green (run 28172615641); planted ruff F401 → `lint + format + types` failed (run 28171942002).
      depends: 0.2.3, 0.3.3
- [x] **0.5.3** Add backend tests+coverage job (`pytest --cov --cov-branch --cov-fail-under=80`) running against the test Postgres.
      verify: a PR dropping coverage below 80% fails the job; the scaffold PR passes. ✓ clean head green incl. integration tests vs Supabase-CLI Postgres (run 28172615641); coverage dropped to 78.42% → `backend tests + coverage` failed (run 28172347219).
      depends: 0.2.4, 0.4.3
- [x] **0.5.4** Add frontend tests+coverage job (vitest v8, 80% thresholds).
      verify: a PR dropping frontend coverage below 80% fails the job; the scaffold PR passes. ✓ clean head green (run 28172615641); coverage dropped to 56.09% → `frontend tests + coverage` failed (run 28172347219).
      depends: 0.3.4
- [x] **0.5.5** Add a build job (API Docker image + web Vite bundle).
      verify: the job builds the API image and the web bundle as artifacts; a broken build fails the job. ✓ clean head green — `api-image` + `web-bundle` artifacts uploaded (run 28172615641); a bad Dockerfile COPY → `build (api image + web bundle)` failed (run 28172347219).
      depends: 0.2.2, 0.3.1
- [x] **0.5.6** Add the E2E job: build the ephemeral stack (web bundle + API container + disposable Postgres seeded with fixtures), run Playwright headless with `LLM_PROVIDER` pointed at FakeLLM, retry-once on flake.
      verify: the E2E job runs the home-page smoke green against the ephemeral stack with no outbound LLM calls (assert zero Groq/Gemini network requests). ✓ run 28172615641 (clean head): seed + API container (`LLM_PROVIDER=fake`, no LLM keys) + disposable Supabase Postgres; `/__test__/llm-calls` `0 → 1` on `/__test__/generate` (deterministic FakeLLM, zero real LLM calls) and Playwright `1 passed`.
      depends: 0.4.2, 0.4.4, 0.5.5
- [x] **0.5.7** Add the security job: pip-audit, pnpm audit, and gitleaks (fail on new criticals/secrets).
      verify: the job runs all three on the scaffold and goes green; a planted dummy secret makes gitleaks fail the job. ✓ pip-audit + pnpm audit + gitleaks green on the clean scaffold (run 28171555344); a planted non-allowlisted secret → gitleaks `leaks found: 2` → `security (audit + secrets)` failed (run 28172118253). (A doc-example AWS key is allowlisted by gitleaks' default config; a real-shaped key trips it.)
- [x] **0.5.8** Add advisory a11y + perf budgets (axe + Lighthouse CI) on the web build, non-blocking to start.
      verify: the job posts axe/Lighthouse results on the PR and does not block merge while advisory. ✓ `a11y + perf (advisory)` runs axe + Lighthouse CI on the web bundle with `continue-on-error: true` (not a required check), so it never blocks merge (run 28172615641).
      depends: 0.3.1
- [x] **0.5.9** Add a coverage-delta PR comment for backend + frontend.
      verify: opening a PR posts a comment showing backend and frontend coverage deltas. ✓ `coverage delta (PR comment)` posted a backend + frontend coverage table on PR #12 (backend 100%/100%, frontend 100%/100%; run 28171555344).
      depends: 0.5.3, 0.5.4
- [ ] **0.5.10** Open a trivial PR and confirm the full required gate is green end to end.
      verify: a no-op PR shows all required checks (lint, types, backend cov, frontend cov, build, E2E, security) passing and is mergeable.
      depends: 0.5.2, 0.5.3, 0.5.4, 0.5.5, 0.5.6, 0.5.7

## 0.6 — Branch protection, PR template & repo hardening  ·  S

_Context: enforce trunk-based flow on `main` and encode the Definition of Done. Several items here are OWNER (Kotlar) actions tracked in ../owner-setup-checklist.html._

- [x] **0.6.1** Add `.github/pull_request_template.md` encoding the Definition of Done checklist from ../09-testing-quality.md (coverage ≥80%, README/OpenAPI updates, observability, security, migration+RLS, cost guard).
      verify: opening a new PR pre-populates the body with the DoD checklist.
- [x] **0.6.2** Document the required-status-checks list and branch-protection policy in the repo (e.g. `infra/branch-protection.md`) so the config is committed, not tribal.
      verify: the doc lists every required check name exactly as it appears in CI and matches the gate in ../09-testing-quality.md. ✓ `infra/branch-protection.md` lists the six required check names verbatim from `.github/workflows/ci.yml` (`lint + format + types`, `backend tests + coverage`, `frontend tests + coverage`, `build (api image + web bundle)`, `e2e (ephemeral stack, FakeLLM)`, `security (audit + secrets)`) + the policy (require PR + 1 approval, required checks, strict/up-to-date, dismiss stale) matching ../09-testing-quality.md.
      depends: 0.5.10
- [ ] **0.6.3** **OWNER (Kotlar) · DEFERRED → [../owner-deferred-tasks.md](../owner-deferred-tasks.md) (non-blocking):** Enable branch protection on `main` — require PR + 1 approval, required status checks, up-to-date branch, dismiss stale approvals. **Do this at the end (before launch)** — turning it on now would break the autonomous self-merge flow. Does not block any implementation.
      verify: `gh api repos/lior-kotlar/lengua/branches/main/protection` returns without 404 and shows `required_pull_request_reviews.required_approving_review_count = 1`; a direct push to `main` is rejected.
      depends: 0.5.10
- [ ] **0.6.4** **OWNER (Kotlar) · DEFERRED → [../owner-deferred-tasks.md](../owner-deferred-tasks.md) (non-blocking):** Enable Dependabot vulnerability alerts + automated security fixes. **Do this at the end (before launch).** Does not block any implementation.
      verify: `gh api repos/lior-kotlar/lengua/vulnerability-alerts -i` returns HTTP 204 (not 404).

## 0.7 — Accounts & CI secrets  ·  S

_Context: every free-tier account already exists and is verified (2026-06-25): GitHub repo + 28 Actions secrets; Supabase staging `rydclyotzdwcbbeyitcx` + prod `ptyqlxjykbprfzhnxgla`; GCP `lengua-prod` + Artifact Registry + `github-ci` SA; Google OAuth in Supabase; Groq/Gemini/Resend/Grafana/Sentry keys as CI secrets; Ben's `.env` + gcloud + Docker. Only the items below remain. Paid store accounts (Apple $99/yr, Google Play $25) are DEFERRED to Phase 7 — not in scope here._

- [x] **0.7.1** GitHub repo + Actions exist; all 28 GitHub Actions secrets present. (Verified 2026-06-25 — do not redo.)
      verify: `gh secret list -R lior-kotlar/lengua` lists 28 secrets.
- [x] **0.7.2** Supabase org + staging (`rydclyotzdwcbbeyitcx`) and prod (`ptyqlxjykbprfzhnxgla`) projects live; email + Google auth providers enabled; anon/service-role keys verified against the JWT secret. (Verified 2026-06-25.)
      verify: both project refs resolve in the Supabase dashboard and CI holds `SUPABASE_STAGING_PROJECT_REF` / `SUPABASE_PROD_PROJECT_REF`.
- [x] **0.7.3** Google Cloud project `lengua-prod` + Artifact Registry `europe-west1-docker.pkg.dev/lengua-prod/lengua` + `github-ci` service account; Ben has `roles/editor`. (Verified 2026-06-25.)
      verify: `gcloud artifacts repositories list --project lengua-prod` shows the `lengua` repo in `europe-west1`.
- [x] **0.7.4** Vercel account + project imported; CI token/IDs set. (Verified 2026-06-25 — Ben dashboard access still pending, see 0.7.9.)
      verify: Vercel project exists in the dashboard and CI holds the Vercel token + project IDs.
- [x] **0.7.5** Groq free-tier key verified working with `llama-3.1-8b-instant` (default LLM for all dev/CI); Gemini key held in CI for the later prod flip. (Verified 2026-06-25.)
      verify: a Groq test call with `llama-3.1-8b-instant` returns 200; `GROQ_API_KEY` and `GEMINI_API_KEY` both present as CI secrets.
- [x] **0.7.6** Grafana Cloud OTLP + Sentry (lengua-api + lengua-web DSNs) + Resend keys all set as CI secrets. (Verified 2026-06-25.)
      verify: `OTLP`, `SENTRY_DSN` (api + web), and Resend secrets all present in `gh secret list`.
- [ ] **0.7.7** **OWNER (Kotlar):** Add the two missing CI secrets `GCP_REGION=europe-west1` and `SENTRY_ORG=kotlar-y7`. (Outstanding per ../owner-setup-checklist.html Task 3.)
      verify: `gh secret list -R lior-kotlar/lengua` shows both `GCP_REGION` and `SENTRY_ORG`.
- [ ] **0.7.8** **OWNER (Kotlar):** Confirm Resend custom SMTP is enabled and delivering in BOTH Supabase projects (staging auto-confirm is OFF, so sign-up emails must work). (Outstanding per ../owner-setup-checklist.html Task 5.)
      verify: a recovery/invite email sent from each project (staging + prod) actually arrives in an inbox.
- [x] **0.7.9** ~~**OWNER (Kotlar):** Invite Ben to Vercel.~~ **RESOLVED 2026-06-25** — on the **free** Vercel tier a project has a single manager seat; Ben (`benartzi4@gmail.com`) is the account holder/manager for `lengua`. Not blocking; proceeding as-is.
      verify: Ben runs `vercel project ls` and `lengua` appears. (Satisfied via the single-manager free-tier account; see ../owner-deferred-tasks.md.)
- [x] **0.7.10** **DONE 2026-06-25** — Ben (`benartzi4@gmail.com`) joined Grafana Cloud + Sentry (both projects: lengua-api, lengua-web).
      verify: Ben can open the Grafana stack and both Sentry projects (lengua-api, lengua-web). ✓
- [x] **0.7.11** Note: paid store accounts (Apple Developer $99/yr, Google Play $25 one-time) are DEFERRED to Phase 7 and intentionally NOT part of Phase 0.
      verify: this deferral is recorded here and in ../08-open-questions-and-costs.md; no Phase 0 task requires a paid account.

## 0.8 — Docs placeholders  ·  S

_Context: create the legal/ops docs the store and runbook phases fill in later._

- [x] **0.8.1** Add `docs/privacy-policy.md` placeholder noting Supabase storage and that vocab/sentences go to the active LLM provider (Groq now / Gemini prod).
      verify: `test -f docs/privacy-policy.md` exits 0 and the file names Supabase + the LLM data flow.
- [x] **0.8.2** Add `docs/runbook.md` placeholder with empty sections for health checks, deploy/rollback, and on-call.
      verify: `test -f docs/runbook.md` exits 0 and the file has the three section headers.

---

## Phase 0 exit gate

Phase 0 is DONE only when all of these hold:

- [ ] Both apps build and run empty — verify: `cd apps/api && uv run uvicorn app.main:app` serves `GET /health` → 200, and `cd apps/web && pnpm build` produces a bundle that serves the placeholder page.
- [ ] The legacy Streamlit app still runs after the restructure — verify: launching the relocated Streamlit entrypoint serves its home page with no ImportError.
- [ ] The per-PR quality gate is green on a trivial PR — verify: a no-op PR shows all required checks (lint, types, backend cov ≥80%, frontend cov ≥80%, build, E2E with LLM stubbed, security) passing and mergeable.
- [ ] Shared test infra works — verify: `uv run pytest` uses the FakeLLM + throwaway Postgres with no outbound LLM/network calls, and the E2E seed produces the demo account.
- [ ] Branch protection + DoD are enforced — verify: a direct push to `main` is rejected, opening a PR pre-fills the DoD template, and `gh api .../branches/main/protection` returns without 404.
- [ ] All required free-tier accounts/secrets are ready — verify: outstanding owner items (0.6.3, 0.6.4, 0.7.7–0.7.10) all pass their checks; `gh secret list` includes `GCP_REGION` and `SENTRY_ORG`; Ben has Vercel/Grafana/Sentry access.
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
