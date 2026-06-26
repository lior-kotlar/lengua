# apps/web — Lengua web app (React + Vite)

The React + TypeScript single-page app: Vite build, `pnpm`, Tailwind CSS + shadcn/ui,
react-router, TanStack Query. Talks to `apps/api` over HTTP (via the typed client) and uses
Supabase only for auth.

Phase-4 group 4.1 built the production **app shell** on top of the Phase-0 scaffold: theming,
routing, server-state, the Supabase client, and the shadcn primitives every screen builds on. The
authenticated screens (Generate / Review / Discover / Languages / Settings / Account) are currently
lightweight stubs that later Phase-4 groups fill in.

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
- **E2E:** Playwright (`e2e/*.spec.ts`), a headless app-shell smoke against the production build.

## Environment

Vite build-time vars (inlined into the bundle). Copy the example and fill in real values:

```bash
cp apps/web/.env.example apps/web/.env
```

| Var                      | Purpose                                                   |
| ------------------------ | --------------------------------------------------------- |
| `VITE_API_BASE_URL`      | Base URL of the Lengua FastAPI backend                    |
| `VITE_SUPABASE_URL`      | Supabase project URL (auth only)                          |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key (auth only; safe in the browser) |

These are validated by `readEnv()` (`src/lib/env.ts`), which **fails fast with a clear error naming
any missing var** the moment the env / Supabase client is loaded. Public pages render without env so
the env-less CI build + home smoke work; any auth-touching screen surfaces a misconfiguration
immediately. Never put a service-role key here.

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

E2E (requires the Chromium browser once):

```bash
pnpm exec playwright install --with-deps chromium
pnpm exec playwright test    # builds, serves preview, runs the app-shell smoke headless
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
    App.tsx               route tree (AuthLayout routes vs AppLayout routes + 404)
    index.css             Tailwind layers + shadcn design tokens
    lib/
      utils.ts            cn() class-merge helper
      env.ts              readEnv() — validate + type VITE_* env (fail-fast)
      supabase.ts         lazy auth-only supabase-js client
      query-client.ts     createQueryClient() — TanStack Query defaults
    components/
      app-layout.tsx      authenticated shell (header / sidebar / content)
      auth-layout.tsx     unauthenticated shell (login / signup)
      nav-items.ts        primary navigation config
      theme-provider.tsx  light/dark/system theming (persisted)
      theme-toggle.tsx    header theme toggle
      use-theme.ts        theme context + useTheme() hook
      placeholder-screen.tsx  stub used by the not-yet-built screens
      ui/                 shadcn-generated primitives (button/card/input/dialog/toast…) — coverage-excluded
    pages/                one component per route (Dashboard/Generate/Review/Discover/
                          Languages/Settings/Account/Login/Signup/NotFound)
    *.test.tsx            Vitest tests (co-located)
  e2e/home.spec.ts        Playwright app-shell smoke
```
