# apps/web — Lengua web app (React + Vite)

The React + TypeScript single-page app: Vite build, `pnpm`, Tailwind CSS + shadcn/ui,
react-router. Talks to `apps/api` over HTTP and uses Supabase only for auth.

Scaffolded in Phase 0 group 0.3. Renders a placeholder home route (`/`) with a sample
shadcn `Button`.

## Toolchain

- **Package manager:** `pnpm` (pinned via the `packageManager` field; if you don't have
  `pnpm` on your PATH, `corepack pnpm <cmd>` works — `corepack` ships with Node).
- **Build:** Vite 6 + React 18 + TypeScript 5.6.
- **UI:** Tailwind CSS 3 + shadcn/ui (`src/components/ui/`), `cn()` helper in `src/lib/utils.ts`.
- **Routing:** react-router (`BrowserRouter` in `src/main.tsx`, routes in `src/App.tsx`).
- **Unit tests:** Vitest + Testing Library + jsdom (`*.test.tsx` under `src/`), v8 coverage
  with an 80% threshold (lines/branches/functions/statements).
- **E2E:** Playwright (`e2e/*.spec.ts`), a single headless home-page smoke against the
  production build.

## Common commands

Run all of these from `apps/web/` (prefix with `corepack ` if `pnpm` isn't on your PATH):

```bash
pnpm install                 # install dependencies
pnpm dev                     # Vite dev server (placeholder home at http://localhost:5173)
pnpm build                   # tsc --noEmit + vite build → dist/
pnpm preview                 # serve the built dist/ locally
pnpm lint                    # eslint
pnpm exec prettier --check . # formatting check (pnpm run format to fix)
pnpm exec tsc --noEmit       # type-check
pnpm test                    # vitest run with v8 coverage (fails under 80%)
pnpm run test --coverage     # same, explicit flag (pnpm needs `run`/`--` before runner flags)
pnpm verify                  # lint + format-check + types + unit(coverage) + build
```

E2E (requires the Chromium browser once):

```bash
pnpm exec playwright install --with-deps chromium
pnpm exec playwright test    # builds, serves preview, runs the home smoke headless
```

## Layout

```
apps/web/
  index.html              Vite entry HTML
  vite.config.ts          Vite + Vitest config (coverage thresholds, e2e excluded)
  tailwind.config.ts      Tailwind theme (shadcn CSS variables)
  components.json         shadcn/ui config
  playwright.config.ts    Playwright config (webServer = build + preview)
  src/
    main.tsx              app bootstrap (BrowserRouter)
    App.tsx               route table
    index.css             Tailwind layers + shadcn design tokens
    lib/utils.ts          cn() class-merge helper
    components/ui/        shadcn-generated components (button.tsx) — coverage-excluded
    pages/Home.tsx        placeholder home route + sample shadcn Button
    *.test.tsx            Vitest render tests (MemoryRouter)
  e2e/home.spec.ts        Playwright home-page smoke
```
