# Staging environment map — Lengua

Research note for staging-validation. Sources: `planning/go-live-activation.md`,
`planning/staging-validation.md`, `.github/workflows/deploy-staging.yml`,
`.github/workflows/seed-staging.yml`, `apps/api/app/settings.py`, `apps/api/app/quota.py`,
`apps/api/scripts/staging_smoke.py`, `apps/web/playwright.staging.config.ts`,
`apps/web/e2e-staging/*`, `.env.example`, `apps/web/.env.example`, `apps/web/.env`.

## TL;DR

- **Staging LLM provider = Groq `llama-3.1-8b-instant`** (`LLM_PROVIDER=groq`, hard-wired in
  `deploy-staging.yml`). Gemini is **prod-only**; FakeLLM is **CI/E2E-only**. So automated
  `POST /generate` / `POST /discover` against staging make **REAL Groq calls** and **count against
  the cost guard**. Groq is a **free tier (no card)** → **dollar cost is effectively $0**, but a
  multi-user automated run **will be throttled/blocked** by the cost guard and Groq's own free-tier
  RPM/RPD (see Risks). There is no path to a surprise bill on staging unless the provider is changed
  to Gemini.
- **Staging is a single Cloud Run instance** (`--max-instances=1`), so the in-process rate limiter,
  global-budget kill-switch, and concurrency semaphore are all accurate.
- CD is **ARMED**: `DEPLOY_ENABLED=true` (set 2026-06-29). Every merge to `main` auto-deploys
  staging (migrate → API → web → smoke).

## URLs / origins

| Thing | Value |
|---|---|
| Staging web origin (Vercel, stable alias) | `https://lengua-staging.vercel.app` (repo var `STAGING_WEB_ORIGIN`) |
| Staging API base URL the **web app uses** | the Cloud Run staging service URL — CD wires `VITE_API_BASE_URL` to the `deploy-api-staging` job output (`needs.deploy-api-staging.outputs.url`) |
| Cloud Run service (canonical URL, smoke default) | `https://lengua-api-staging-cxiyhzhria-ew.a.run.app` |
| Cloud Run service (equivalent project-number URL, in go-live doc) | `https://lengua-api-staging-1083154360111.europe-west1.run.app` |
| Cloud Run service name / region / project | `lengua-api-staging` / `europe-west1` / GCP `lengua-prod` |
| Supabase staging | project ref `rydclyotzdwcbbeyitcx`, `https://rydclyotzdwcbbeyitcx.supabase.co` (West EU/Ireland) |
| Demo / reviewer account | `demo@lengua.test` / `demo-password-123` (seeded; ~12 ES + 6 HE/RTL cards) |

The locally-checked-in `apps/web/.env` points `VITE_API_BASE_URL` at `http://localhost:8000`
(local API) but `VITE_SUPABASE_URL/ANON_KEY` at **staging** Supabase — that file is the go-live §A
local fast-path, NOT the deployed staging config.

## Env vars — WEB (`apps/web`, Vite build-time, client-safe only)

Set in CD `deploy-web-staging` (canonical home = Vercel project env, `preview`=staging):

- `VITE_API_BASE_URL` = staging Cloud Run URL (from the API deploy job output)
- `VITE_SUPABASE_URL` = `SUPABASE_STAGING_URL` secret
- `VITE_SUPABASE_ANON_KEY` = `SUPABASE_STAGING_ANON_KEY` secret (browser-safe by design)
- `VITE_SENTRY_DSN_WEB` = `SENTRY_DSN_WEB` secret
- `VITE_SENTRY_ENVIRONMENT=staging` (override — `vercel build` always reports MODE=production)
- Optional / owner follow-up: `VITE_OAUTH_PROVIDERS=google` (S2 — hides the dead Apple button),
  `VITE_POSTHOG_KEY`, `VITE_SENTRY_TRACES_SAMPLE_RATE`. Never a service-role/LLM/JWT secret here.

## Env vars — API (Cloud Run runtime, from `deploy-staging.yml` → `cloud-run-deploy`)

- `LLM_PROVIDER=groq`
- `GROQ_API_KEY` = secret (Groq free-tier operator key, shared across all users)
- `DATABASE_URL` = `SUPABASE_STAGING_DATABASE_URL` secret — **session pooler** host
  (`aws-0-eu-west-1.pooler.supabase.com:5432`, IPv4, port 5432 = session mode NOT 6543)
- `SUPABASE_URL` = `SUPABASE_STAGING_URL`
- `SUPABASE_SERVICE_ROLE_KEY` = `SUPABASE_STAGING_SERVICE_ROLE_KEY` (account-deletion path only)
- `SUPABASE_JWT_SECRET` = `SUPABASE_STAGING_JWT_SECRET` (legacy HS256 fallback)
- `SUPABASE_JWKS_URL` = `<SUPABASE_STAGING_URL>/auth/v1/.well-known/jwks.json` — **required**:
  Supabase signs access tokens with **ES256/JWKS**, so without this the API 401s every real token
- `ENV=staging`, `DEPLOYMENT_ENVIRONMENT=staging`
- `SENTRY_DSN_API`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` (observability live)
- `CORS_ALLOW_ORIGINS` = `STAGING_WEB_ORIGIN` repo var (exactly `https://lengua-staging.vercel.app`,
  never a wildcard; only added when the repo var is set)

Cloud Run flags: `--allow-unauthenticated --port=8080 --min-instances=0 --max-instances=1
--concurrency=40 --cpu=1 --memory=512Mi --timeout=60`, startup+liveness probes on `/health`.

**The cost-guard env vars are NOT set in CD**, so staging runs the code **defaults** below.

## LLM provider selection seam

`app/deps.py:get_llm_provider` → `lengua_core.llm.get_provider()` reads `LLM_PROVIDER`:
`groq` / `gemini` (real, need a key) or `fake` (deterministic `FakeLLM`, CI/E2E). Staging = `groq`.

## LLM cost guard — limits in effect on staging (code defaults; `apps/api/app/settings.py`)

Gate chain order (`app/quota.py`): **email-verified → rate-limit → daily-cap → global-budget**.
Increment-on-success only (a failed/blocked provider call never burns budget; no refund path).

| Limit | Default (staging) | Effect when hit |
|---|---|---|
| `MAX_GENERATE_PER_DAY` | 50 | hard server ceiling /user/day (clamps user override) |
| `MAX_DISCOVER_PER_DAY` | 30 | hard server ceiling /user/day |
| `MAX_EXPLAIN_PER_DAY` | 100 | hard server ceiling /user/day (cache-miss only) |
| `DEFAULT_GENERATE_PER_DAY` | 20 | per-user default generate cap (no override) → **429 `daily_cap_reached`** |
| `DEFAULT_DISCOVER_PER_DAY` | 10 | per-user default discover cap → 429 `daily_cap_reached` |
| `DEFAULT_EXPLAIN_PER_DAY` | 50 | per-user default explain cap |
| `NEW_ACCOUNT_DAY0_GENERATE_CAP` | 5 | new account's FIRST UTC day generate cap = `min(cap, 5)` |
| `RATE_LIMIT_PER_MIN` | 10 | per-user sliding window across ALL kinds → **429 `rate_limited`** + `Retry-After` |
| `LLM_MAX_CONCURRENCY` | 4 | max in-flight provider calls per process → **503 `server_busy`** + short `Retry-After` |
| `GLOBAL_DAILY_BUDGET` | 1000 | project-wide successful LLM calls/day (ALL users) → **429 `daily_limit_reached`** ("Daily limit reached, please try again tomorrow.") until UTC rollover |
| `MAX_WORDS_PER_REQUEST` | 30 | `/generate` word-list cap → **422** if exceeded (hard reject, pre-provider) |
| `DISCOVER_REUSE_WINDOW_SECONDS` | 300 | repeated identical `/discover` returns cached preview, no provider call / no count |

Global budget rationale: set below Groq free RPD ÷ 3 (retry fan-out). One counted call can fan out
to up to 3 real Groq HTTP requests on 429/5xx (`lengua_core/llm/retry.py` DEFAULT_MAX_ATTEMPTS=3),
so 1000 → ≤3000 worst-case requests, under Groq `llama-3.1-8b-instant`'s few-thousand/day free tier.

## How to avoid paid usage / cost-guard breakage in an automated run

- **No dollar cost on staging** as long as `LLM_PROVIDER=groq` (free tier). The only paid-LLM risk
  is if someone flips staging to Gemini — don't.
- **Skip real-LLM calls when you don't need them:** API smoke supports `--no-llm` /
  `SMOKE_INCLUDE_LLM=0`; the web `e2e-staging` specs are **structure-only** and never click Generate
  (they only assert the form renders), so they burn **zero** LLM.
- **Cost guard treated as success in smoke:** `staging_smoke.py` maps a 429/503 on the generate /
  discover probes to PASS (cost-guard firing is correct behavior).
- **For a multi-user generation load test:** prefer FakeLLM (the Phase-3 zero-paid-usage load test
  used FakeLLM). Against live staging you cannot swap the provider, so expect the caps to throttle:
  per-user 20 generate/day (5 on a day-0 account), 10 req/min, global 1000 successful calls/day, and
  Groq's own ~30 RPM / ~1K RPD free limits. Seed/distribute across accounts and stay within the
  global budget to avoid tripping the day-wide kill-switch for everyone.

## Smoke / E2E suites and how to run them locally against staging

**API smoke** — `apps/api/scripts/staging_smoke.py` (non-destructive; only write is a throwaway
language created+deleted; never grades a card or deletes the account). NOT wired into CI.
```
cd apps/api
STAGING_SUPABASE_ANON_KEY=<staging anon key> uv run python scripts/staging_smoke.py
# options: --no-llm (skip real Groq probes) | --json | --timeout N
# env overrides: STAGING_API_URL (default the Cloud Run staging URL),
#   STAGING_SUPABASE_URL (default rydclyotzdwcbbeyitcx), DEMO_EMAIL/DEMO_PASSWORD,
#   STAGING_BEARER_TOKEN (skip GoTrue login), SMOKE_INCLUDE_LLM (default 1)
```
Probes: `/health`, `/ready`, `/feature-flags`, login (GoTrue password grant), `/me`, `/languages`,
`/review/due`, `/settings`, `/account/export`, POST+DELETE `/languages`, then the gated real-LLM
`/discover` + `/generate`. Exit 0 unless a required endpoint FAILs (SKIP is not a failure).

**Web E2E (live-staging Playwright)** — `apps/web/e2e-staging/` via
`apps/web/playwright.staging.config.ts` (no `webServer`; hits the live origin; 1 retry; generous
timeouts). NOT in CI. Structure-only (auth.spec, screens.spec — review/generate/languages/settings).
```
cd apps/web
corepack pnpm install
PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app corepack pnpm test:e2e-staging
# default base URL is already https://lengua-staging.vercel.app
# DEMO_EMAIL/DEMO_PASSWORD env-overridable; consent banner pre-dismissed in fixtures
```

## CD pipeline / GitHub Actions

- `.github/workflows/deploy-staging.yml` — trigger: `push` to `main`. Gated
  `if: ${{ vars.DEPLOY_ENABLED == 'true' }}` (now true; unset = green no-op skip). Jobs:
  `build-push` (image SHA+`staging` tags → Artifact Registry) → `migrate-staging`
  (`alembic -x env=staging upgrade head`) → `deploy-api-staging` (Cloud Run, via local
  `./.github/actions/cloud-run-deploy`) → `deploy-web-staging` (Vercel preview build + deploy +
  `vercel alias set` to `STAGING_WEB_ORIGIN`) → `smoke-staging` (local `./.github/actions/cloud-run-smoke`
  probes `/health`+`/ready`+web 200; fails the run on any failed probe). `concurrency: deploy-staging`,
  no cancel.
- `.github/workflows/seed-staging.yml` — **manual** `workflow_dispatch` only; idempotent demo-only
  seed (`scripts/seed_e2e.py`); independent of `DEPLOY_ENABLED`.
- `.github/workflows/deploy-prod.yml` — separate gated prod promotion (also `DEPLOY_ENABLED`-gated +
  GitHub `production` environment approval). Has the same JWKS/IPv6-pooler caveats; prod DB URL still
  the direct IPv6 host as of go-live doc (must swap to session pooler before prod migrate).
- `.github/workflows/ci.yml` — the FakeLLM gate (never touches live staging / no real LLM).
- `DEPLOY_ENABLED=true` set via `gh variable set DEPLOY_ENABLED -b true` (go-live §E, 2026-06-29).
  Last verified green: run 28405320398; staging_smoke 13/0/0 + e2e-staging 6/6 (per MEMORY/§E).

## Verified-working state (from `staging-validation.md`, 2026-06-30)

Full core loop green end-to-end on live staging against real Groq (login → generate → save → review
→ discover → settings → languages → account-export). Auth ES256→JWKS verified, CORS bound to the
Vercel origin, kill-switch honored, no cross-tenant leakage, **no real-LLM overspend observed**.
Open hardening items tracked as S1–S21 (S1 right-to-erasure FK = highest).
