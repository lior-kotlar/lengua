# apps/web — React web app

The React + TypeScript (Vite) UI. One codebase serves the web app and, wrapped by
Capacitor, the iOS/Android apps. Scaffold lands in Phase 0 group 0.3; parity with the
legacy Streamlit app is reached in Phase 4; native wrapping happens in Phase 7.

Planned layout (see [planning/01-architecture.md](../../planning/01-architecture.md)):

```
apps/web/
  src/
  capacitor.config.ts   # Capacitor wrap config (Phase 7)
  ios/  android/        # generated native projects (Phase 7)
```

Tooling: `pnpm`, Vite, Tailwind + shadcn/ui, eslint + prettier, `tsc`, vitest (≥80% gate),
Playwright E2E. Auth is via `supabase-js`; all domain calls go to `apps/api`.
