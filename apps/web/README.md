# apps/web — Lengua web app (React + Vite)

The React + TypeScript single-page app: Vite build, `pnpm`, Tailwind CSS + shadcn/ui,
react-router, TanStack Query. Talks to `apps/api` over HTTP (via the typed client) and uses
Supabase only for auth.

Phase-4 group 4.1 built the production **app shell** on top of the Phase-0 scaffold: theming,
routing, server-state, the Supabase client, and the shadcn primitives every screen builds on. Group
4.3 added **auth & session handling** (below). The authenticated screens (Generate / Review /
Discover / Languages / Settings / Account) are currently lightweight stubs that later Phase-4 groups
fill in.

## Auth & sessions (group 4.3)

Signup is required — there is no guest mode. Auth uses `supabase-js` (sessions/tokens/OAuth only);
all application data goes through the typed API client.

- **Routes:** `/login`, `/signup`, `/forgot-password` (public, redirect into the app if already
  signed in), `/reset-password` + `/auth/callback` (consume a transient recovery / verification
  session, so they are _not_ redirect-guarded). All authenticated routes sit behind `RequireAuth`,
  which redirects signed-out users to `/login` (remembering where they were heading).
- **Auth context:** `AuthProvider` (`components/auth-provider.tsx`) reads the existing session on
  load and subscribes to auth changes; `useAuth()` exposes `{ user, session, loading }`. On
  sign-out it resets the TanStack Query cache so no previous user's data lingers.
- **Auth seam:** `lib/auth.ts` wraps every supabase-js call (sign-up / log-in / OAuth / password
  reset / sign-out / resend), builds the redirect URLs from the current origin, and maps raw GoTrue
  errors to friendly, code-tagged messages (so the UI can, e.g., offer a resend CTA for an
  unverified email).
- **Token refresh + 401 retry:** the API client (`lib/api-client.ts`) refreshes the session once on
  a 401 and retries the request (single-flight, at most one retry); if the refresh fails it signs
  out, which clears the cache and redirects to `/login`.
- **OAuth:** Google + Apple buttons appear on both auth screens. Live credentials are owner-only, so
  they degrade gracefully (a friendly error on click, or a disabled "(soon)" button when narrowed
  via `VITE_OAUTH_PROVIDERS`).

## Toolchain

- **Package manager:** `pnpm` (pinned via the `packageManager` field; if you don't have
  `pnpm` on your PATH, `corepack pnpm <cmd>` works — `corepack` ships with Node).
- **Build:** Vite 6 + React 18 + TypeScript 5.6.
- **UI:** Tailwind CSS 3 + shadcn/ui (`src/components/ui/`), `cn()` helper in `src/lib/utils.ts`,
  lucide-react icons.
- **Routing:** react-router v6 (`BrowserRouter` in `src/main.tsx`, route tree in `src/App.tsx`).
- **Server state:** TanStack Query (`createQueryClient` in `src/lib/query-client.ts`); React Query
  Devtools load in dev only.
- **Theming:** `ThemeProvider` (`src/components/theme-provider.tsx`) with shadcn CSS-variable
  tokens; light / dark / system, persisted to localStorage, toggled via `ThemeToggle`.
- **Auth:** `@supabase/supabase-js` — AUTH ONLY (`getSupabaseClient()` in `src/lib/supabase.ts`,
  created lazily on first use). All application data goes through the API, never Supabase data APIs.
- **Unit tests:** Vitest + Testing Library + jsdom (`*.test.tsx` under `src/`), v8 coverage with an
  80% threshold (lines/branches/functions/statements) over product code (`main.tsx`,
  `components/ui/**`, and test files are excluded).
- **E2E:** Playwright (`e2e/*.spec.ts`) — a route-gating smoke against the env-less build, plus
  authenticated auth flows against the ephemeral stack (see "E2E harness" below).

## Environment

Vite build-time vars (inlined into the bundle). Copy the example and fill in real values:

```bash
cp apps/web/.env.example apps/web/.env
```

| Var                      | Purpose                                                               |
| ------------------------ | --------------------------------------------------------------------- |
| `VITE_API_BASE_URL`      | Base URL of the Lengua FastAPI backend                                |
| `VITE_SUPABASE_URL`      | Supabase project URL (auth only)                                      |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key (auth only; safe in the browser)             |
| `VITE_OAUTH_PROVIDERS`   | _optional_ — comma-separated OAuth providers to enable (default both) |

These are validated by `readEnv()` (`src/lib/env.ts`), which **fails fast with a clear error naming
any missing var** the moment the env / Supabase client is loaded. The app still renders without env
(the env-less CI build + route-gating smoke work — `AuthProvider` degrades to signed-out, so `/`
redirects to `/login`); any auth-touching action surfaces a misconfiguration. Never put a
service-role key here.

## Common commands

This app is part of the root **pnpm workspace** (`pnpm-workspace.yaml`, with `packages/*`), so
there is a single `pnpm-lock.yaml` at the repo root. Run these from `apps/web/` (prefix with
`corepack ` if `pnpm` isn't on your PATH); `pnpm install` resolves the whole workspace whether you
run it here or at the root:

```bash
pnpm install                 # install workspace dependencies (web + packages/*)
pnpm dev                     # Vite dev server (http://localhost:5173)
pnpm build                   # tsc --noEmit + vite build → dist/
pnpm preview                 # serve the built dist/ locally
pnpm lint                    # eslint
pnpm format:check            # prettier --check (pnpm format to fix)
pnpm typecheck               # tsc --noEmit
pnpm test                    # vitest run with v8 coverage (fails under 80%)
pnpm verify                  # lint + format-check + types + unit(coverage) + build
```

## E2E harness

Playwright specs live in `e2e/` and run in two tiers:

- **Route-gating smoke** (`a logged-out visit to / redirects to the login screen`) runs anywhere.
  Even the env-less local preview renders, because `AuthProvider` degrades to signed-out when the
  Supabase env is absent — so `/` redirects to `/login`. This is what `pnpm exec playwright test`
  runs locally (it builds + previews the env-less bundle itself).
- **Authenticated flows** (sign-up → verify-notice; demo log-in → home; sign-out re-gates) need the
  real **ephemeral stack** — Supabase (CLI) + the API container with `LLM_PROVIDER=fake` and **no
  LLM keys** — and the web bundle **built against that stack**. They are gated on `E2E_STACK=1` and
  use the seeded demo account (`apps/api/scripts/seed_e2e.py`).

The CI `e2e` job wires this up (`.github/workflows/ci.yml`): start Supabase → run the API container
(FakeLLM, `SUPABASE_JWT_SECRET` from the stack so it verifies real tokens) → seed the demo account →
assert zero real LLM calls → **build the web bundle with `VITE_API_BASE_URL` / `VITE_SUPABASE_URL` /
`VITE_SUPABASE_ANON_KEY` pointing at the stack** (not the env-less `build`-job artifact, which stays
for a11y/perf) → `vite preview` + `playwright test` with `E2E_STACK=1`. The zero-real-LLM guarantee
is preserved (the container has no Groq/Gemini keys; the FakeLLM call counter is asserted).

The 401 → refresh-once → retry path (task 4.3.7) is verified exhaustively in vitest
(`src/lib/api-client.test.ts`) rather than E2E (a mid-session 401 against a healthy API is not
reliably reproducible).

Run it locally (Chromium installed once):

```bash
pnpm exec playwright install --with-deps chromium
pnpm exec playwright test            # env-less route-gating smoke (stack flows auto-skip)

# Full auth flows against a running stack (from repo root):
supabase start
eval "$(supabase status -o env | sed 's/^/export /')"
( cd apps/api && DATABASE_URL="$DB_URL" SUPABASE_URL="$API_URL" \
    SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY" uv run python scripts/seed_e2e.py )
VITE_API_BASE_URL=http://127.0.0.1:8000 VITE_SUPABASE_URL="$API_URL" \
  VITE_SUPABASE_ANON_KEY="$ANON_KEY" pnpm build
pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort &
E2E_STACK=1 PLAYWRIGHT_TEST_BASE_URL=http://127.0.0.1:4173 pnpm exec playwright test
```

## Layout

```
apps/web/
  index.html              Vite entry HTML
  .env.example            required VITE_* env vars (copy to .env)
  vite.config.ts          Vite + Vitest config (coverage thresholds, e2e excluded)
  tailwind.config.ts      Tailwind theme (shadcn CSS variables)
  components.json         shadcn/ui config
  playwright.config.ts    Playwright config (webServer = build + preview)
  src/
    main.tsx              app bootstrap (ThemeProvider → QueryClientProvider → BrowserRouter)
    App.tsx               route tree (auth routes + guards vs AppLayout routes + 404)
    index.css             Tailwind layers + shadcn design tokens
    lib/
      utils.ts            cn() class-merge helper
      env.ts              readEnv() — validate + type VITE_* env (fail-fast)
      supabase.ts         lazy auth-only supabase-js client
      api-client.ts       typed API client (bearer inject + 401 refresh/retry + typed errors)
      auth.ts             auth seam over supabase-js (signup/login/oauth/reset/signout + error map)
      auth-validation.ts  client-side email/password validation (mirrors the server policy)
      query-client.ts     createQueryClient() — TanStack Query defaults
    components/
      app-layout.tsx      authenticated shell (header / sidebar / content / account menu)
      auth-layout.tsx     unauthenticated shell (login / signup / reset)
      auth-context.ts     AuthContext + useAuth() hook
      auth-provider.tsx   session bootstrap + auth-state subscription + cache reset on sign-out
      auth-card.tsx       titled card scaffold for the auth screens
      form-field.tsx      labeled input + inline validation message
      route-guards.tsx    RequireAuth / RedirectIfAuthed / RouteLoader
      oauth-buttons.tsx   Google + Apple OAuth buttons (graceful degradation)
      user-menu.tsx       header account email + sign-out
      nav-items.ts        primary navigation config
      theme-provider.tsx  light/dark/system theming (persisted)
      theme-toggle.tsx    header theme toggle
      use-theme.ts        theme context + useTheme() hook
      placeholder-screen.tsx  stub used by the not-yet-built screens
      ui/                 shadcn-generated primitives (button/card/input/dialog/toast…) — coverage-excluded
    pages/                one component per route (Dashboard/Generate/Review/Discover/Languages/
                          Settings/Account + Login/Signup/ForgotPassword/ResetPassword/AuthCallback/NotFound)
    *.test.tsx            Vitest tests (co-located)
  e2e/auth.spec.ts        Playwright auth + route-gating E2E (env-less smoke + stack flows)
```
