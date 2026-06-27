# Go-Live Activation & Validation — owner-run (Ben + Kotlar)

> **What this is:** the **owner-run** track that turns the as-code Phase 6 CD pipeline + the
> already-provisioned accounts/secrets into a **live, watchable web app**, with a **validation
> gate on every step**. It sits **between Phase 6 (build the CD as-code) and Phase 7 (mobile)**.
>
> **NOT executed by the autonomous `/run-phase` agent driver** — every step needs the live
> accounts/secrets and must be human-validated. Agents only assist a step on explicit request.
>
> **Rule:** do not advance to the next step until the current step's `verify:` passes
> ("validate before"). Work **staging fully green → then prod**.
>
> Completing §G also closes the deferred **Phase 5** live observability verifies
> ([outstanding-work.md §11](outstanding-work.md)).

---

## Status snapshot — verified via CLI on 2026-06-27

**Already provisioned (inputs ✅):**
- **GCP** project `lengua-prod` (gcloud authed as benartzi4@gmail.com); deployer SA in `GCP_SA_JSON`; **Artifact Registry repo `lengua` (DOCKER) exists**.
- **Supabase** both projects exist, EU: `lengua-staging` (West EU/Ireland, ref `rydclyotzdwcbbeyitcx`, CLI-linked) + `lengua-prod` (Central EU/Frankfurt, ref `ptyqlxjykbprfzhnxgla`).
- **GitHub Actions secrets** — full set: `GCP_PROJECT_ID/REGION/SA_JSON`, `VERCEL_TOKEN/ORG_ID/PROJECT_ID`, `SUPABASE_STAGING_*` + `SUPABASE_PROD_*` (URL/ANON/SERVICE_ROLE/JWT/DB_URL/PROJECT_REF) + `SUPABASE_ACCESS_TOKEN`, `RESEND_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS`, `SENTRY_DSN_API/WEB`, `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `GROQ_API_KEY`, `GEMINI_API_KEY`.
- Local `.env`: Groq key, staging Supabase (DB/URL/anon/service-role/JWT), both Sentry DSNs. **DB reachable** (`select 1` OK).
- **Correction to stale tracking:** `GCP_REGION` + `SENTRY_ORG` secrets ARE set now (memory/outstanding-work still list them open — fix on landing).

**Missing — purely the outputs of a deploy that has never run (❌):**
1. **Staging Supabase DB has no schema** — `public` has 0 tables, no `alembic_version`. (Prod likely same.)
2. **No Cloud Run service** — `lengua-api-staging/prod` absent in every EU region (registry+SA+project ready, just nothing deployed).
3. **No Vercel project** linked/deployed — `vercel projects ls` empty, no `.vercel/project.json` (token/org/project secrets exist).
4. **No `apps/web/.env`** — only `.env.example`; the web app has no local config.
5. **CD pipeline as-code** — in progress (Phase 6 workflow, group G6) + `DEPLOY_ENABLED` repo variable not set.
6. Minor: `pnpm` not installed locally (repo uses `corepack pnpm`).

---

## A. Watch it locally NOW (fast path, ~10 min) — staging Supabase + local servers · **Ben**

The quickest way to *see and click* the real app today, before any deploy. Runs the real API +
web locally against the hosted **staging** Supabase.

- **A1 — Apply the schema to staging.** From `apps/api`, run Alembic against the staging DB
  (Alembic is the schema source of truth and its 0002/0003/0004 revisions add the trigger + RLS +
  kill-switch, which apply on Supabase because it has the `authenticated` role + `auth.uid()`):
  `uv run alembic -x db_url="$SUPABASE_STAGING_DATABASE_URL" upgrade head`
  **verify:** `psql "$URL" -c '\dt'` lists the 8 app tables + `llm_usage`/`llm_budget`; `select version_num from alembic_version` == `alembic heads`.
- **A2 — Confirm RLS + trigger landed.** **verify:** `pytest apps/api/tests/test_rls.py` (pointed at staging) proves two users can't read each other's rows; a fresh signup auto-creates exactly one `profiles` row (`plan='free'`).
- **A3 — Seed the demo/reviewer account.** `uv run python apps/api/scripts/seed_e2e.py` (idempotent). **verify:** run twice → no duplicate rows; the demo account logs in and `GET /review/due` returns ≥1 due card.
- **A4 — Create `apps/web/.env`** (gitignored): `VITE_API_BASE_URL=http://localhost:8000`, `VITE_SUPABASE_URL=<staging URL>`, `VITE_SUPABASE_ANON_KEY=<staging anon>` (optional: `VITE_SENTRY_DSN_WEB`, `VITE_OAUTH_PROVIDERS=google`). **verify:** `corepack pnpm --filter web build` passes the env validator.
- **A5 — Run both servers.** API: `uv run uvicorn app.main:app --port 8000` (from `apps/api`, `.env` loaded). Web: `corepack pnpm --filter web dev`. **verify (the watch):** open `http://localhost:5173`, log in as the demo account, and walk **generate → save → review (reveal + 4 ratings) → discover** end-to-end against staging.

> Caveat: A4's `apps/web/.env` is local-only; CORS on the API already allows `localhost:5173`.

---

## B. Deploy the API to Cloud Run — **staging** · **Ben** (uses the as-code CD once it lands)

- **B1 — Build + push image** to `…-docker.pkg.dev/lengua-prod/lengua` tagged with the commit SHA. **verify:** `gcloud artifacts docker images list …/lengua` shows the SHA tag.
- **B2 — Apply staging migrations** as a discrete step (skip if A1 done). **verify:** `alembic current` == `heads` against `SUPABASE_STAGING_DATABASE_URL`.
- **B3 — Deploy `lengua-api-staging`** in the `GCP_REGION` EU region (scale-to-zero, min 0), mounting runtime config: `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `DATABASE_URL=<staging>`, `SUPABASE_URL/JWT_SECRET/SERVICE_ROLE_KEY`, `OTEL_EXPORTER_OTLP_*`, `SENTRY_DSN_API`, quota ceilings. **verify:** `gcloud run services describe lengua-api-staging` → `Ready`; `curl <url>/health` 200; `curl <url>/ready` 200 (DB reachable).
- **B4 — Runtime SA = `secretmanager.secretAccessor` only.** **verify:** a generate call against the staging URL returns sentences (Groq), and the SA can't read unrelated secrets.

---

## C. Deploy the web to Vercel — **staging** · **Ben**

- **C1 — Link `apps/web`** (`vercel link` with `VERCEL_ORG_ID`/`PROJECT_ID`; root dir `apps/web`, install/build via `corepack pnpm`). **verify:** the project appears in `vercel projects ls`.
- **C2 — Set Vercel env (staging), client-safe only:** `VITE_API_BASE_URL=<staging Cloud Run URL>`, `VITE_SUPABASE_URL/ANON_KEY` (staging), `VITE_SENTRY_DSN_WEB`, optional `VITE_POSTHOG_KEY`. **verify:** `vercel env ls` shows **no** service-role / LLM / JWT secret.
- **C3 — Deploy.** **verify:** the staging web URL serves 200; log in as demo; the full loop works against the staging API. **← this is the staging "watch it on web".**

---

## D. Supabase Auth wiring — **staging** · **Ben (config) + Kotlar (DNS/SMTP)**

- **D1 — Redirect/allow-list URLs** = staging web origin (+ `capacitor://localhost`, `app.lengua://` for later). **verify:** an email-confirmation link returns to the staging web origin; an un-listed redirect is refused.
- **D2 — Custom SMTP (Resend) + SPF/DKIM/DMARC** on the sending domain (`RESEND_API_KEY` ready). **verify:** a staging signup email arrives via Resend (provider dashboard), not the Supabase built-in sender. *(Kotlar owns the DNS records.)*
- **D3 — API CORS allow-list** = exactly the staging web origin, no wildcard. **verify:** `pytest tests/test_cors.py`; allowed origin gets headers, disallowed rejected.
- **D4 — (optional) Google OAuth** (creds in `GOOGLE_OAUTH_*`). **verify:** Google sign-in completes on staging. *(Apple deferred to Phase 7 — paid account.)*

---

## E. Turn on CD: merge-to-main → staging auto-deploy · **Ben** (after the Phase 6 CD PR merges)

- **E1 — Set repo variable `DEPLOY_ENABLED=true`** (`gh variable set DEPLOY_ENABLED -b true`) — the committed CD jobs are gated off until this flips. **verify:** a trivial merge to `main` triggers the staging deploy run → green smoke probes (`/health`, `/ready`, web 200).
- **E2 — Discrete migrate + Vercel steps run.** **verify:** the run logs show a distinct "migrate-staging" (`alembic upgrade head`) job and a "vercel-staging" job; staging serves the new SHA.

---

## F. Prod promotion (gated) · **Ben deploys, Kotlar approves** — only after staging is signed off

- **F1 — Apply prod DB schema** (gated/manual first time, `SUPABASE_PROD_DATABASE_URL`). **verify:** `alembic current` == `heads`; `\dt` lists tables.
- **F2 — Supabase **prod** Auth** (redirect/SMTP/OAuth) + API CORS = prod origins. **verify:** as §D against prod origins.
- **F3 — Promote the **exact staging-validated image digest** to `lengua-api-prod`** (no rebuild), behind the GitHub `production` environment approval. **verify:** prod revision digest == staging's; `/health` + `/ready` 200.
- **F4 — Deploy web prod (Vercel production).** **verify:** the prod web URL serves; full loop works. **← prod "watch it on web".**
- **F5 — Rollback drill.** **verify:** the runbook rollback script shifts 100% traffic to the previous revision (`/health` 200 from the old code); ≥2 revisions retained.

---

## G. Close the deferred Phase 5 live observability verifies (now that it's deployed) · **Ben + Kotlar**

Each is as-code-done; this lights up the live half (see [outstanding-work.md §11](outstanding-work.md)).

- **G1** — trace appears in Grafana Tempo, searchable by `service.name=lengua-api` (5.1.5); per-route p95 in Mimir (5.2.6).
- **G2** — structured log line in Loki filtered by `service_name=lengua-api` (5.3.1); Tempo→Loki trace-to-logs jump (5.3.3).
- **G3** — RED / cost-guard / product dashboards render non-empty after a load script (5.6.1–3); infra dashboard wired (5.6.4).
- **G4** — Sentry API + web issues, `trace_id` opens the matching Tempo trace (5.4.1/5.4.2); Sentry alert rule → channel (5.4.3).
- **G5** — Grafana alert rules fire to a real Slack/Discord/email channel (5.7.1–5); external uptime monitor flips DOWN + notifies (5.8.1).
- **G6** — PostHog (EU) ingests the 4 consent-gated funnel events (5.9.1/5.9.2); build funnel/retention/feature insights (5.9.3).

---

## Ownership split

| Doer | Scope |
|---|---|
| **Ben** (CLIs already authed: gcloud / supabase / vercel / gh) | schema apply, image build/push, Cloud Run deploys, Vercel link/deploy, CORS, `DEPLOY_ENABLED`, all validation `verify:` runs, local fast-path (§A). |
| **Kotlar** (account admin / paid / dashboards) | Resend SMTP + SPF/DKIM/DMARC DNS, Grafana/Sentry/PostHog dashboard + alert-channel config, **approve prod promotion** (GitHub `production` env reviewer), Apple/Play accounts + domain (Phase 7). |

## Cross-links
- Phase 6 as-code tasks (CD workflows, Dockerfile, /ready, feature flags): [tasks/phase-6-infra-cicd.md](tasks/phase-6-infra-cicd.md)
- Owner-deferred live verifies (Phase 5): [outstanding-work.md §11](outstanding-work.md); (Phase 6): §12.
- Infra design (locked decisions): [05-infra-deploy.md](05-infra-deploy.md)
