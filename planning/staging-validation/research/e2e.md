# E2E / browser / smoke test inventory — Lengua

Research note for staging validation. Catalogs every end-to-end / browser / smoke suite in the
repo, how each is run, what it targets, and how the LLM is supplied. (`.claude/worktrees/**` are
stale agent copies — ignored throughout.)

There is **NO Selenium / Cypress / Puppeteer** anywhere. All browser testing is **Playwright**.
There are exactly **three** suites, plus a curl-only deploy smoke action:

| # | Suite | Path | Runner | Target | LLM | In CI? |
|---|-------|------|--------|--------|-----|--------|
| 1 | Local/CI Playwright e2e | `apps/web/e2e/` | `pnpm e2e` | local vite preview (`:4173`) | FakeLLM + browser route-stubs | **Yes** (`ci.yml` `e2e` job) |
| 2 | Live-staging Playwright | `apps/web/e2e-staging/` | `pnpm test:e2e-staging` | `https://lengua-staging.vercel.app` | real Groq (but never invoked) | **No** (on-demand) |
| 3 | API staging smoke | `apps/api/scripts/staging_smoke.py` | `uv run python scripts/staging_smoke.py` | Cloud Run staging API | **real Groq** (gated) | **No** (on-demand) |
| – | Deploy smoke (curl) | `.github/actions/cloud-run-smoke/action.yml` | composite GH action | deployed API + web | none (probes `/health`,`/ready`, web 200) | in deploy-staging/prod |

---

## 1. Local / CI Playwright e2e — `apps/web/e2e/` (the FakeLLM gate)

Config: **`apps/web/playwright.config.ts`** (full text):

```ts
const PORT = 4173;
const EXTERNAL_BASE_URL = process.env.PLAYWRIGHT_TEST_BASE_URL;
const BASE_URL = EXTERNAL_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,   // serialized to 1 worker under CI
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: BASE_URL, trace: 'on-first-retry' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: EXTERNAL_BASE_URL
    ? undefined                              // external base URL → no local server
    : {
        command: `npx vite build && npx vite preview --port ${PORT} --strictPort`,
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: { VITE_ENABLE_DEBUG_TOOLS: '1' }, // exposes the hidden Sentry debug button
      },
});
```

- **Browser/projects:** chromium only (Desktop Chrome). **Retries:** 1 under CI, 0 local.
  **Workers:** 1 under CI (serialized), default (parallel) locally. **Reporter:** `github` in CI,
  `list` locally. **testDir:** `./e2e`. **webServer:** builds + serves the bundle on `:4173`
  itself, UNLESS `PLAYWRIGHT_TEST_BASE_URL` is set (CI sets it and serves the bundle externally).
- **Run:** `pnpm --filter @lengua/web e2e` / `npm --prefix apps/web run e2e` (script `e2e` =
  `playwright test`).
- **Base URL:** local `http://localhost:4173` (CI serves on `http://127.0.0.1:4173` and passes it
  via `PLAYWRIGHT_TEST_BASE_URL`). **Never targets staging.**

### Spec files (12) and flows
- `full-loop.spec.ts` — **the Phase-4 exit-gate "full core loop" spec** named in CLAUDE.md:
  login (demo) → Generate 2 timestamp-unique words → save (4 cards) → Review (reveal + grade
  **Again**) → Discover preview. Gated `E2E_STACK=1`. No Streamlit; every LLM step hits the real
  server seam (FakeLLM).
- `auth.spec.ts` — route-gating smoke (runs env-less: logged-out `/` → `/login`, OAuth button
  states) + `E2E_STACK` flows (signup→verify-notice; demo login→Dashboard; sign-out re-gates).
- `generate.spec.ts` — generate→select subset→save→assert saved cards become due (calls API
  directly with captured bearer token); also a **browser-stubbed 429** daily-limit panel test.
- `review.spec.ts` — counts header, reveal, grade via mouse + keyboard, tap-a-word popover.
- `discover.spec.ts` — real-FakeLLM preview ("house" always present); reroll + accept + 429 are
  **browser route-stubbed**.
- `languages.spec.ts` — add/scope/override CEFR/remove a throwaway language (unique per run).
- `settings.spec.ts` — change daily-new-card limit, persist across reload; bounds validation.
- `account.spec.ts` — real `GET /account/export` download; delete dialog with **DELETE stubbed at
  the browser boundary** (shared demo account is never actually deleted).
- `rtl.spec.ts` — Hebrew RTL/nikkud: `dir=rtl`, Noto Sans Hebrew loaded, vowel-marks toggle,
  RTL-aware tap-a-word (touch + click).
- `consent.spec.ts` — first-run analytics banner; **plain preview, no auth/stack**, uses RAW
  `@playwright/test`.
- `sentry.spec.ts` — hidden Sentry debug button fires capture path with **zero egress**; plain
  preview, no auth/stack, RAW `@playwright/test`.
- `fixtures.ts` — shared `test` that pre-seeds `localStorage['lengua.analytics-consent']='denied'`
  via `addInitScript` (keeps the consent overlay off bottom-anchored controls).

### How the LLM is supplied (suite 1)
- Authed/stack specs run against an **API container with `LLM_PROVIDER=fake` and NO Groq/Gemini
  keys** → deterministic FakeLLM, real-LLM call is impossible. FakeLLM does no I/O.
- 429 / reroll / delete edge cases are **stubbed at the browser boundary** (`page.route`) — the
  server LLM seam is never reached.
- `consent`/`sentry` run on the plain preview (no stack at all).
- Most authed specs are gated `test.skip(process.env.E2E_STACK !== '1')`; the env-less route-gating
  / consent / sentry checks always run.

### CI wiring (`.github/workflows/ci.yml`, job `e2e`, ~lines 321–503)
1. `supabase start` → disposable Postgres + Auth; captures `DB_URL/API_URL/ANON_KEY/SERVICE_ROLE_KEY/JWT_SECRET`.
2. `uv run python scripts/seed_e2e.py` seeds the demo account into the disposable DB.
3. Loads the API image built earlier, runs it with `LLM_PROVIDER=fake`, no LLM keys,
   `SUPABASE_JWKS_URL` (ES256/JWKS verification), `CORS_ALLOW_ORIGINS=http://127.0.0.1:4173`.
4. **Zero-real-LLM proof:** asserts the FakeLLM call counter goes `0 → >0` via
   `/__test__/llm-calls` + `/__test__/generate`.
5. Rebuilds the web bundle wired to the ephemeral stack (`VITE_API_BASE_URL=http://127.0.0.1:8000`,
   stack `VITE_SUPABASE_*`, `VITE_ENABLE_DEBUG_TOOLS=1`), serves it on `127.0.0.1:4173`, then
   `pnpm exec playwright test` with `CI=true E2E_STACK=1 PLAYWRIGHT_TEST_BASE_URL=http://127.0.0.1:4173`.
6. Tears down container + Supabase; uploads `playwright-report` on failure.

---

## 2. Live-staging Playwright — `apps/web/e2e-staging/` (the staging browser re-validation)

Config: **`apps/web/playwright.staging.config.ts`** (full text):

```ts
const BASE_URL =
  process.env.PLAYWRIGHT_TEST_BASE_URL ?? 'https://lengua-staging.vercel.app';

export default defineConfig({
  testDir: './e2e-staging',
  fullyParallel: true,                       // each spec logs in independently
  forbidOnly: !!process.env.CI,
  retries: 1,                                // absorbs cold-start / network flake
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 90_000,                           // cold Cloud Run + real login
  expect: { timeout: 20_000 },
  use: {
    baseURL: BASE_URL,
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // NOTE: NO webServer — it hits the live deployed origin; never builds/serves anything.
});
```

- **Browser/projects:** chromium only. **Retries:** 1 (always). **Workers:** default/parallel
  (CI=1 but it never runs in CI). **Reporter:** `list`. **testDir:** `./e2e-staging`. **No
  webServer** — drives the real deployed site. Generous timeouts for Cloud Run cold start.
- **Run:** `pnpm --filter @lengua/web test:e2e-staging` /
  `npm --prefix apps/web run test:e2e-staging` (script `test:e2e-staging` =
  `playwright test --config playwright.staging.config.ts`).
- **Base URL:** defaults to **`https://lengua-staging.vercel.app`**; override with
  `PLAYWRIGHT_TEST_BASE_URL` (this is exactly how you point it at any other origin/preview).
- **Explicitly excluded from CI**, the default `playwright test`, vitest, and coverage (per config
  docstring) so the gate never touches live staging.

### Spec files (2 files → 6 tests; matches the "e2e-staging 6/6 green" in MEMORY)
- `auth.spec.ts` (2 tests): logged-out `/` → `/login`; demo login → app shell (Primary nav).
- `screens.spec.ts` (4 tests): Review (deck **or** graceful empty state); Generate form renders;
  Languages lists ≥1 (or empty msg); Settings preferences form renders.
- `fixtures.ts`: shared `login(page)` helper + consent pre-dismissal; demo creds are
  **env-overridable** via `DEMO_EMAIL` / `DEMO_PASSWORD` (default `demo@lengua.test` /
  `demo-password-123`).

### Key property: structure-only / read-only
Every assertion checks STRUCTURE (headings, nav, form fields, or a graceful empty state) — never
exact copy or seeded data, and **never triggers a generate/discover** (no LLM call). It stays green
whether or not staging has been seeded. **The LLM provider on staging is real Groq, but these specs
never invoke it**, so they incur zero real-LLM cost.

---

## 3. API staging smoke — `apps/api/scripts/staging_smoke.py` (the "staging_smoke" suite)

- **What it is:** a standalone Python `httpx` script (NOT pytest, never imported by the test suite,
  never wired into CI). Sweeps every Lengua API endpoint as the demo user against **LIVE staging**
  and prints a per-endpoint PASS/FAIL/SKIP table (or `--json`). Exit 0 unless any required endpoint
  FAILs (SKIP is not a failure).
- **Run:** `cd apps/api && uv run python scripts/staging_smoke.py`
  (`--no-llm` / `SMOKE_INCLUDE_LLM=0` to skip the real-LLM probes; `--timeout`, `--json`).
- **Target (env, with staging defaults):**
  - `STAGING_API_URL` default `https://lengua-api-staging-cxiyhzhria-ew.a.run.app` (Cloud Run)
  - `STAGING_SUPABASE_URL` default `https://rydclyotzdwcbbeyitcx.supabase.co`
  - `STAGING_SUPABASE_ANON_KEY` **required** for the GoTrue password-grant login (unless
    `STAGING_BEARER_TOKEN` is supplied to skip login)
  - `DEMO_EMAIL` / `DEMO_PASSWORD` default the seeded demo account.
- **Endpoints covered:** `/health`, `/ready`, `/feature-flags` (unauth); then login → `/me`,
  `/languages`, `/review/due`, `/settings`, `/account/export`; a POST+DELETE `/languages`
  round-trip; and the two real-LLM probes `POST /discover` + `POST /generate`.
- **How the LLM is supplied:** **REAL Groq** (this is the live deployed API). The two LLM probes are
  gated behind `SMOKE_INCLUDE_LLM` (default ON), kept to one trivial word, and a `429` (cost-guard)
  or `503` (backoff) on them is treated as **PASS** (the guard firing is correct behavior).

---

## Deploy smoke (not a test suite, but the CI/CD gate) — `.github/actions/cloud-run-smoke`

Composite GH action used by `deploy-staging.yml` (job `smoke-staging`) and `deploy-prod.yml`.
**curl-only**: polls `${API_URL}/health` then `/ready` (retry ~60s each), then the web root for a
`200`. No auth, no LLM. This is the deploy pipeline's health gate — distinct from the three test
suites above.

---

## Test users / data: creation & cleanup

**Single shared seed for all suites:** `apps/api/scripts/seed_e2e.py` (idempotent).
- Creates demo auth user `demo@lengua.test` / `demo-password-123` via the Supabase **Auth Admin
  API** (`email_confirm=true`; the `handle_new_user` trigger makes the `profiles` row), one Spanish
  language + 3 sentences → 6 due cards (recognition+production), and a vowelized **Hebrew** language
  + 6 nikkud cards for the RTL specs. Re-running finds the existing user and uses
  `ON CONFLICT`/existence checks → never duplicates.
- **CI (suite 1):** seeds the **disposable** Supabase each run; the whole stack (container +
  Supabase) is torn down at job end (`docker rm -f` + `supabase stop --no-backup`). Nothing persists.
- **Staging (suites 2 & 3):** seeded by the **`seed-staging.yml`** workflow (`workflow_dispatch`
  only, idempotent, demo-account-only; maps `SUPABASE_STAGING_*` secrets → the env `seed_e2e.py`
  reads). The demo account is **persistent and shared** — it is never deleted.

**Cleanup / non-destructiveness against the SHARED staging demo account:**
- `staging_smoke.py`: only write is a uniquely-named throwaway language (`zz-smoke-<ts>`) created
  then immediately DELETEd; never grades a card, never persists a settings change, never calls
  `DELETE /account`.
- `e2e-staging/*`: structure/read-only — no writes at all.
- Suite-1 specs (run only on the ephemeral CI stack, never staging) are still written to be
  repeat-safe on a shared demo deck: timestamp-unique generated words, grade **"Again"** (FSRS keeps
  cards due, deck never depletes), `DELETE /account` and reroll/429 **stubbed at the browser
  boundary**, throwaway language created-then-removed.

---

## Parallel safety against ONE shared staging environment

- **`e2e-staging` (suite 2): safe to run fully parallel.** Config sets `fullyParallel: true` and the
  docstring states "Each spec logs in independently, so they can run in parallel against the live
  site." All 6 tests authenticate as the **same** demo user (independent browser contexts — fine),
  make **structure-only / read-only** assertions, and trigger **no LLM** call → no shared-state
  mutation, no cost-guard contention. Locally it uses the default (multi-)worker pool.
- **`staging_smoke.py` (suite 3):** a single sequential script (no internal parallelism); its lone
  write is a per-timestamp-unique throwaway language, so even two concurrent invocations won't
  collide on names.
- **Caveats when running things in parallel as the SAME demo user on ONE staging env:**
  1. **Cost guard / rate limits are per-user and in-process.** Staging runs Cloud Run with
     `--max-instances=1`, and the Phase-3 rate limiter + discover cache are in-process (single
     instance keeps them accurate). So any **real-LLM-triggering** work (generate/discover —
     `staging_smoke` with LLM on, or manual flows) shares **one** per-user daily cap + rate-limit
     budget across all parallel actors and can `429` each other. `staging_smoke` treats that 429 as
     PASS; `e2e-staging` avoids it entirely (no LLM). Do **not** fan out many real-LLM probes as the
     demo user in parallel.
  2. All actors share the one demo deck/account; keep parallel work read-only or
     uniquely-named-then-cleaned (as the existing suites do) to stay non-destructive.
- **Suite 1 in CI** sidesteps sharing entirely: each run gets a fresh **ephemeral** Supabase + API,
  and `workers: 1` under CI serializes the specs anyway.

---

## How to point Playwright specs at the staging URL (quick reference)

```bash
# Live-staging browser pass (defaults to https://lengua-staging.vercel.app):
npm --prefix apps/web run test:e2e-staging
# …or override the origin (e.g. a Vercel preview):
PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app \
  npm --prefix apps/web run test:e2e-staging
# Override demo creds if needed:
DEMO_EMAIL=demo@lengua.test DEMO_PASSWORD=demo-password-123 \
  npm --prefix apps/web run test:e2e-staging

# API smoke (real Groq probes on; set the anon key for login):
cd apps/api && STAGING_SUPABASE_ANON_KEY=<anon> uv run python scripts/staging_smoke.py
#   add SMOKE_INCLUDE_LLM=0  to skip the real-LLM probes.
```

The default `apps/web/e2e/` config can also be pointed at any served bundle via
`PLAYWRIGHT_TEST_BASE_URL`, but those specs assume the **FakeLLM** ephemeral stack (and most are
gated on `E2E_STACK=1`), so they are NOT appropriate to run against live staging — use
`e2e-staging` for staging.
