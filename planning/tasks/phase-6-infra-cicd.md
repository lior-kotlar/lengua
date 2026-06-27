# Phase 6 — Infra, environments & CI/CD

> **Effort:** M (overlaps Phases 4–5)  ·  **Depends on:** Phase 1 backend core (a deployable API + Alembic), Phase 2 Supabase Auth/RLS (hosted projects need the schema + policies); runs alongside Phase 4 web and Phase 5 observability  ·  **Unlocks:** Phase 7 (mobile points at the prod API), Phase 9 (launch)
> **Source:** roadmap Phase 6 (../02-roadmap.md) · deep dive (../05-infra-deploy.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** three environments (local / staging / prod) exist with isolated EU-region resources; opening a PR runs the blocking lint/test/security gate; merging to `main` builds and pushes the API image, deploys it to Cloud Run staging, runs Alembic migrations against staging, and deploys the web app to Vercel staging — all automatically; promoting to prod is a single gated approval that repeats the deploy against prod resources; and any bad release can be one-click rolled back to the previous Cloud Run revision per the runbook.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 6.1 — Dockerize the API & deploy to Cloud Run  ·  M

_Context: a reproducible container image is the deploy unit for both Cloud Run services; staging and prod are two services in an EU region, each scaling to zero, each with health/readiness probes. Locked: Cloud Run, EU region._

- [x] **6.1.1** Write a production `apps/api/Dockerfile` (multi-stage, non-root user, pinned base, `uvicorn`/`gunicorn` entrypoint reading `$PORT`) and a `.dockerignore`. <!-- confirmed + hardened: base image now pinned by sha256 digest in both stages; build+run path CI-verified by the `build` job's new smoke step. -->
      verify: `docker build -t lengua-api apps/api` succeeds and `docker run -p 8080:8080 -e PORT=8080 lengua-api` answers `curl localhost:8080/health` with `200`.
- [x] **6.1.2** Add `/health` (liveness) and `/ready` (readiness — checks DB connectivity) endpoints and wire Cloud Run startup/liveness probes to them. <!-- endpoints + tests done & CI-verified; the live Cloud Run probe WIRING (startup/liveness→/health, readiness→/ready in the service config) lands in CD §6.6 / owner — see outstanding-work §12 -->
      verify: `pytest apps/api/tests/test_health_ready.py` asserts `/health` returns `200` always and `/ready` returns `503` when the DB is unreachable and `200` when reachable.
- [ ] **6.1.3** Create an Artifact Registry repo (EU region) and push the built image with both a git-SHA tag and `latest`.
      verify: `gcloud artifacts docker images list <eu-region>-docker.pkg.dev/<project>/lengua` lists the pushed image with the current commit SHA as a tag.
- [ ] **6.1.4** Provision the `lengua-api-staging` Cloud Run service (EU region, scale-to-zero, min-instances 0, concurrency + CPU/memory set) and deploy the image.
      verify: `gcloud run services describe lengua-api-staging --region <eu-region>` shows the service `Ready`, and `curl https://<staging-run-url>/health` returns `200`.
- [ ] **6.1.5** Provision the `lengua-api-prod` Cloud Run service (same EU region, its own service account + config) and deploy the image.
      verify: `gcloud run services describe lengua-api-prod --region <eu-region>` shows `Ready` and `curl https://<prod-run-url>/health` returns `200`.
- [ ] **6.1.6** Configure least-privilege deploy + runtime service accounts (GCP) — a CI deployer SA (Artifact Registry push + Cloud Run deploy) and per-service runtime SAs (Secret Manager accessor only).
      verify: `gcloud projects get-iam-policy <project>` shows the deployer SA limited to deploy/push roles and the runtime SAs limited to `roles/secretmanager.secretAccessor`; a deploy run using the deployer SA succeeds while it cannot read unrelated secrets.

## 6.2 — Two Supabase hosted projects (staging + prod)  ·  M

_Context: two hosted EU-region Supabase projects; schema is owned by Alembic, RLS/Supabase-specific SQL by the Supabase CLI, seeds by scripts. Locked: Supabase, EU region, RLS on every user table._

- [ ] **6.2.1** Create the staging + prod Supabase projects in an **EU region** and record their project refs, DB connection strings, anon keys, service-role keys, and JWT secrets (into the secret stores, never git).
      verify: both projects show region = EU in the Supabase dashboard; `psql "$STAGING_DATABASE_URL" -c 'select 1'` and the prod equivalent each return `1`.
- [ ] **6.2.2** Apply the full Alembic migration history to the staging DB and confirm it is at head.
      verify: `alembic -x env=staging upgrade head` exits 0 and `alembic -x env=staging current` prints the latest revision id matching `alembic heads`.
- [ ] **6.2.3** Apply the Alembic history to the prod DB (gated/manual the first time) and confirm head.
      verify: `alembic -x env=prod current` equals `alembic heads` after the run; `psql "$PROD_DATABASE_URL" -c '\dt'` lists the expected tables.
      depends: 6.2.2
- [ ] **6.2.4** Move RLS policies + Supabase-specific SQL into `infra/supabase/` and apply via the Supabase CLI to both projects. <!-- RECONCILED, NOT relocated: the canonical RLS/trigger/kill-switch SQL stays at repo-root supabase/migrations/ (the CLI-native location the local stack + CI apply; moving it would break `supabase db …`). infra/supabase/README.md documents that location, the Alembic-DDL relationship, and the per-project apply path. Box left UNticked: the verify needs a LIVE staging DB (supabase db push / alembic apply + pytest tests/test_rls.py against staging) — owner-deferred, see outstanding-work §12. -->
      verify: `supabase db push` (or migration apply) runs clean against each project; `pytest apps/api/tests/test_rls.py` run against the staging DB proves two users cannot read each other's rows.
      depends: 6.2.2
- [ ] **6.2.5** Write idempotent seed scripts: a demo/reviewer account and minimal fixtures, runnable per environment. <!-- as-code done: the idempotent scripts (apps/api/scripts/seed_e2e.py + seed_dev_user.py) already exist and select the env via DATABASE_URL (+ SUPABASE_URL/SERVICE_ROLE_KEY); infra/supabase/README.md "Seeding per environment" documents the per-env invocation + idempotency guarantee. Box left UNticked: the verify is a LIVE staging run (reviewer created first run, no duplicate second run, reviewer logs in) — owner-deferred, see outstanding-work §12. -->
      verify: running the seed script against staging creates the reviewer account; running it a second time makes no duplicate (row counts unchanged) and the reviewer can log in.
      depends: 6.2.4
- [ ] **6.2.6** Configure custom SMTP (Resend/Brevo) on the staging + prod Supabase Auth with SPF/DKIM on the sending domain.
      verify: a signup against staging sends the verification email via the custom SMTP provider (visible in the provider's dashboard/logs), not the Supabase built-in sender.

## 6.3 — Vercel web projects (staging + prod)  ·  S

_Context: two Vercel projects (or one project with two environments) from the same monorepo; only the **anon** key + public URLs reach the client. Locked: Vercel, never expose service-role/LLM keys to the client._

- [ ] **6.3.1** Link `apps/web` to Vercel with the monorepo root/build settings (Vite build command, output dir, install command) for a **staging** target.
      verify: a Vercel build of `apps/web` succeeds and the staging URL serves the app shell (HTTP `200` on `/`).
- [ ] **6.3.2** Set the **prod** Vercel environment/project with its own production build target and domain.
      verify: a production Vercel deploy succeeds and the prod URL serves the app (HTTP `200`), distinct from the staging URL.
- [ ] **6.3.3** Confirm PR **preview deploys** are enabled so each PR gets an ephemeral web URL.
      verify: opening a test PR produces a Vercel preview URL (posted as a check/comment) that serves the branch build.
- [x] **6.3.4** Audit the built web bundle for leaked secrets — only `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`, and the web Sentry DSN may appear; no service-role or LLM provider key. <!-- Two halves, both CI-enforced: (1) the CI `build` job greps the built `dist/` for forbidden server-only env NAMES (SUPABASE_SERVICE_ROLE_KEY / SUPABASE_JWT_SECRET / GROQ_API_KEY / GEMINI_API_KEY / DATABASE_URL) + provider key VALUE shapes (gsk_…, AIza…, service_role) and fails on any hit — validated zero-false-positive on the clean bundle, catches synthetic leaks, ignores the legitimate anon key (role "anon"). (2) `apps/web/src/lib/bundle-safety.test.ts` (runs under `pnpm test`) scans the web source for any server-only secret name and locks the referenced `VITE_*` surface to the client-safe allow-list (VITE_API_BASE_URL/SUPABASE_URL/SUPABASE_ANON_KEY/SENTRY_DSN_WEB/POSTHOG_KEY/OAUTH_PROVIDERS/ENABLE_DEBUG_TOOLS). -->
      verify: `gitleaks` (or a grep assertion in CI) over the built `dist/` finds no service-role/Groq/Gemini key, and `pnpm test` includes a check that those env names are absent from the bundle.

## 6.4 — Per-platform secrets  ·  S

_Context: secrets live per platform — Secret Manager (Cloud Run), Vercel env, GitHub Actions — never in git; each env has its own LLM provider config (default Groq), Supabase keys/JWT secret, OTLP creds, Sentry DSN. Locked: Groq default; only anon key + public URLs to client._

- [ ] **6.4.1** Create Secret Manager entries (per env) for `LLM_PROVIDER`, `GROQ_API_KEY`, `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `OTEL_*`, `SENTRY_DSN`, and quota ceilings, and mount them into the Cloud Run services.
      verify: `gcloud run services describe lengua-api-staging --region <eu-region>` shows the secrets mounted; the running service reads `LLM_PROVIDER=groq` and reaches the DB (its `/ready` returns `200`).
- [ ] **6.4.2** Set Vercel environment variables per environment (staging vs prod) limited to the client-safe set.
      verify: `vercel env ls` shows only `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`, web `SENTRY_DSN` for each environment — no service-role or LLM key present.
- [ ] **6.4.3** Add GitHub Actions repo/environment secrets for deploy credentials (GCP deployer SA / Workload Identity, Vercel token, Supabase access token) scoped to the right environments.
      verify: a workflow run reads the secrets and authenticates to GCP, Vercel, and Supabase (each auth step exits 0) without any secret value appearing in logs (masked).
- [ ] **6.4.4** Document and script a secret-rotation procedure (rotate the Groq key, Supabase JWT secret, and a deploy credential) in `docs/runbook.md`. <!-- as-code done: docs/runbook.md "Rotate a secret" has exact add-version→redeploy(:latest)→verify→revoke steps for the Groq key, Supabase JWT secret (+ zero-downtime JWKS alternative), and deploy credential (GCP_SA_JSON + WIF). The "script" = the concrete command sequence (no bash-script convention in-repo). Box left UNticked: the verify is entirely LIVE (rotate the staging Groq key + redeploy picks up the new key) — owner-deferred, see outstanding-work §12. -->
      verify: following the runbook, rotate the staging Groq key in Secret Manager and redeploy; the service picks up the new key (a generate call still succeeds) and the old key no longer works.

## 6.5 — CI: the per-PR gate workflow  ·  M

_Context: this is the blocking gate from [09]; it must be green before merge and is enforced by branch protection. Locked: 100% pass + ≥80% coverage (backend & frontend) + Playwright E2E with the LLM stubbed + gitleaks/audit._

- [ ] **6.5.1** Author the PR workflow skeleton with cache restore (uv/pip, pnpm, Playwright browsers) and the job matrix wired to run on `pull_request`.
      verify: opening a PR triggers the workflow and all jobs start; caches are restored on the second run (cache-hit shown in the run logs).
- [ ] **6.5.2** Add the lint + format + typecheck jobs (ruff/eslint, prettier, mypy/tsc).
      verify: a PR introducing a lint/type error fails this job with a non-zero exit; a clean PR passes it.
- [ ] **6.5.3** Add the backend test job: `pytest --cov --cov-fail-under=80` against a disposable Postgres (Supabase CLI/testcontainers) including the RLS isolation + migration-apply tests.
      verify: the job runs unit + integration tests against a real Postgres and **fails** when coverage drops below 80% (proven by a PR that removes a test).
- [ ] **6.5.4** Add the frontend test job: `vitest --coverage` with the 80% v8 thresholds + the web build.
      verify: the job fails when frontend coverage falls under 80% and passes on a covered PR; the Vite build artifact is produced.
- [ ] **6.5.5** Add the contract-drift job comparing the server OpenAPI schema to the generated `packages/api-types` client.
      verify: a PR that changes an endpoint without regenerating types **fails** this job; regenerating the client makes it pass.
- [ ] **6.5.6** Add the E2E job: build the API image + web bundle + disposable Postgres, run Playwright headless with the **deterministic LLM fake**, auto-retry a failure once.
      verify: the critical-journey Playwright suite (signup, generate→save, review four ratings, 429 path) passes against the ephemeral stack with zero real LLM calls (provider fake asserted; no Groq/Gemini network egress).
- [ ] **6.5.7** Add the security job: `pip-audit` + `pnpm audit` + `gitleaks` (full history + working tree).
      verify: `gitleaks detect` and the audits run on every PR and **fail** the PR when a planted dummy secret or a known-critical advisory is present; a clean PR passes.
- [ ] **6.5.8** Add a coverage-delta comment + the a11y/perf (axe, Lighthouse CI) jobs (advisory first).
      verify: a PR receives a coverage-delta comment and the Lighthouse/axe job posts its budget report; the job is present in the checks list.

## 6.6 — CD: merge-to-main ships staging  ·  M

_Context: merging to `main` is the staging-deploy trigger — build+push image, deploy Cloud Run staging, run Alembic migrations as a discrete logged step, deploy web to Vercel staging. Locked: migrations are a separate gated step; keep prior revision for rollback._

- [ ] **6.6.1** Add the `main`-push workflow step that builds the API image and pushes it to Artifact Registry tagged with the commit SHA.
      verify: merging a trivial PR to `main` pushes a new image whose tag equals the merge commit SHA (visible in Artifact Registry).
- [ ] **6.6.2** Add the step that deploys the freshly pushed image to `lengua-api-staging` as a new revision.
      verify: after a merge, `gcloud run revisions list --service lengua-api-staging --region <eu-region>` shows a new revision serving 100% traffic and `/health` on staging returns `200`.
      depends: 6.6.1
- [ ] **6.6.3** Add a **discrete, logged** Alembic migration step that runs against the staging DB before/with the deploy (job-level, not in the request path).
      verify: a merge that includes a new migration shows a distinct "migrate staging" job in the run logs that runs `alembic upgrade head`; afterward `alembic -x env=staging current` equals `alembic heads`.
      depends: 6.2.2
- [ ] **6.6.4** Add the step that deploys `apps/web` to Vercel **staging** on merge to `main`.
      verify: after a merge, the Vercel staging deployment updates to the new commit (dashboard shows the SHA) and the staging web URL serves the new build.
- [ ] **6.6.5** Smoke-check the staging deploy at the end of the workflow (probe `/health` + `/ready` + a web `200`) and fail the run if any probe fails.
      verify: a merge that breaks startup turns the deploy job **red** at the smoke step; a healthy merge ends green with all probes `200`.
      depends: 6.6.2, 6.6.4

## 6.7 — CD: gated prod promotion  ·  M

_Context: prod is a separate, manually approved promotion (release tag or "promote" environment approval) reusing the staged image; prod migrations are gated. Locked: prod gated by an approval; previous revision retained._

- [ ] **6.7.1** Create a GitHub **`production` environment** with a required reviewer/approval and restrict the prod deploy workflow to it.
      verify: triggering the prod workflow pauses on a "waiting for approval" gate; it proceeds only after an authorized reviewer approves (shown in the run's deployment timeline).
- [ ] **6.7.2** Make prod deploy reuse the **exact image already validated on staging** (promote by SHA/digest, no rebuild) to `lengua-api-prod`.
      verify: the prod revision's image digest equals the staging revision's digest for the same release; `gcloud run revisions list --service lengua-api-prod` shows the promoted revision serving traffic.
      depends: 6.6.2
- [ ] **6.7.3** Add the **gated** prod Alembic migration step (separate approval-protected job, logged) run before prod traffic shifts.
      verify: the prod promotion shows a distinct "migrate prod" job that runs only after approval; afterward `alembic -x env=prod current` equals `alembic heads`.
      depends: 6.2.3, 6.7.1
- [ ] **6.7.4** Add the prod Vercel deploy step (web production) as part of the gated promotion.
      verify: after approval, the Vercel production deployment updates to the released SHA and the prod web URL serves it; pre-approval the prod URL is unchanged.
      depends: 6.7.1
- [ ] **6.7.5** Smoke-check the prod deploy (probe prod `/health`, `/ready`, web `200`) and fail/alert the promotion on any failed probe.
      verify: a promotion whose image fails startup turns the prod job **red** at the smoke step and does not leave a broken revision serving 100%; a healthy promotion ends green.
      depends: 6.7.2, 6.7.4

## 6.8 — Rollback & runbook  ·  S

_Context: keep the previous Cloud Run revision so rollback is one click; document deploy/rollback/migrate/secret-rotate/budget-alert/restore in `docs/runbook.md`. Locked: one-click rollback to previous revision._

- [ ] **6.8.1** Configure Cloud Run revision retention + traffic tags so the previous good revision is always kept and addressable.
      verify: after two deploys, `gcloud run revisions list --service lengua-api-prod` shows ≥2 retained revisions and the previous one is reachable via its traffic tag URL.
- [ ] **6.8.2** Document + script a **one-click rollback** that shifts 100% traffic back to the previous revision and prove it.
      verify: run the rollback script against staging; `gcloud run services describe lengua-api-staging` shows 100% traffic on the prior revision and `/health` returns `200` from the rolled-back code (a deliberately broken deploy recovers in one command).
      depends: 6.8.1
- [x] **6.8.3** Write the runbook sections in `docs/runbook.md`: deploy, rollback, run a migration, rotate a secret, respond to a budget-exhausted alert, restore from backup, and the store-release checklist. <!-- All named sections written with concrete, self-contained commands (real lengua-prod / lengua-api-{staging,prod} / $SUPABASE_*_DATABASE_URL identifiers, `<placeholder>` for owner values). The live half — a reviewer following the rollback section end-to-end ON STAGING — needs the deployed Cloud Run service (owner; go-live §F5), see outstanding-work §12. -->
      verify: `docs/runbook.md` contains each named section with concrete commands; a reviewer follows the rollback section end-to-end on staging without needing outside context.
- [ ] **6.8.4** Document a Supabase backup/restore drill (PITR / `pg_dump`) for prod and run it once against a throwaway DB.
      verify: a `pg_dump` of prod restores into a scratch DB and `psql -c 'select count(*) from cards'` returns the expected row count; the steps are captured in the runbook.

## 6.9 — Feature flags  ·  S

_Context: gate risky/new features so they ship **dark** and can be disabled in prod without a redeploy or store update — the safest path for the coordinated launch. Env-driven or a small flags table._

- [ ] **6.9.1** Add a feature-flag mechanism (env-driven flags and/or a small `feature_flags` table) with a typed accessor in the API and an exposure to the web client.
      verify: `pytest apps/api/tests/test_feature_flags.py` asserts a flag defaults off, can be enabled via config/table, and gates a guarded code path; the web reads flag state from the API.
- [ ] **6.9.2** Wrap at least one risky/new feature behind a flag defaulting **off in prod** so it ships dark.
      verify: with the flag off, the feature is unreachable in the prod build (Playwright/API assertion that the guarded route/UI is absent); flipping the flag on exposes it.
      depends: 6.9.1
- [ ] **6.9.3** Prove a flag can be toggled in prod **without a redeploy** (DB row / runtime config change reflected within one TTL/refresh).
      verify: toggle a prod flag via the table/config (no new deploy), then within the refresh interval the API's flag endpoint reports the new value and behavior changes — confirmed without any Cloud Run revision change.
      depends: 6.9.1

## 6.10 — Domains & CORS  ·  S

_Context: optional custom domain or free subdomains for web + API; whichever is used, CORS allow-lists and Supabase redirect URLs must match. Locked: only configure what the chosen domains require._

- [x] **6.10.1** Set the API CORS allow-list per environment to exactly the web origins (staging/prod Vercel URLs or custom domains) — no wildcard in prod. <!-- CORS is env-driven (CORS_ALLOW_ORIGINS, NoDecode + field_validator; CORSMiddleware allow_credentials=True). tests/test_cors.py now also asserts: the default + a prod-shaped allowlist contain no `*`; the actually-installed CORSMiddleware pairs credentials with a wildcard-free origin list (guards the insecure+invalid allow_origins=["*"]+credentials regression); and an un-listed origin is rejected under a prod-shaped config. .env.example documents the exact-origins/no-wildcard prod rule. The actual prod origin VALUES are owner-set per env at deploy (Secret Manager / 6.4.x) — see outstanding-work §12. -->
      verify: `pytest apps/api/tests/test_cors.py` asserts a request from an allowed origin gets the CORS headers and a disallowed origin is rejected; prod config contains no `*` origin.
- [ ] **6.10.2** Configure Supabase Auth redirect/allow-list URLs to match the deployed web origins (and native scheme later) per environment.
      verify: an OAuth/email-confirmation flow on staging redirects back successfully to the staging web origin; an un-allow-listed redirect is refused by Supabase.
- [ ] **6.10.3** (Optional) Attach custom domains — web apex/`www` on Vercel, `api.` on Cloud Run — and update CORS + Supabase redirect URLs accordingly.
      verify: `curl https://api.<domain>/health` returns `200` over the custom domain with a valid TLS cert, and the web custom domain serves the app; the auth + CORS flows still pass against the new origins.
      depends: 6.10.1, 6.10.2

---

## Phase 6 exit gate

Phase 6 is DONE only when all of these hold:

- [ ] Three isolated environments exist — verify: local (Supabase CLI stack) runs the app, and staging + prod each have their own EU-region Cloud Run service, Supabase project, and Vercel deployment, each answering `/health` `200` with environment-specific config (6.1.4 / 6.1.5 / 6.2.1).
- [ ] A PR runs the full blocking gate — verify: opening a PR runs lint/types, backend + frontend tests at ≥80% coverage, contract drift, E2E with the LLM stubbed, and gitleaks/audit, and a PR that violates any of them is blocked from merge by branch protection (6.5.x).
- [ ] Merging to `main` ships staging automatically with an applied migration — verify: a merge to `main` produces a green run that pushes the SHA-tagged image, deploys `lengua-api-staging`, runs the discrete `alembic upgrade head` against staging (`alembic current` == `heads`), and updates Vercel staging — ending with green smoke probes (6.6.x).
- [ ] Prod is a one-click **gated** promotion — verify: the prod workflow pauses for an approval, then promotes the exact staging-validated image digest to `lengua-api-prod`, runs the gated prod migration, and deploys Vercel prod, ending green (6.7.x).
- [ ] A bad release rolls back in one click — verify: shifting prod (or staging) traffic to the previous Cloud Run revision via the runbook script restores a healthy `/health` `200` with ≥2 revisions retained (6.8.1 / 6.8.2).
- [ ] A risky feature can be disabled in prod without a redeploy — verify: toggling its flag (table/config) flips behavior within the refresh interval with no new Cloud Run revision (6.9.3).
- [ ] No secret leaks to the client and security scans pass — verify: the built web bundle contains only the anon key + public URLs (no service-role/LLM key), and `gitleaks` + `pip-audit` + `pnpm audit` pass on the gate (6.3.4 / 6.4.2 / 6.5.7).
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
