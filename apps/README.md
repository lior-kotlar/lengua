# apps/

Deployable applications.

- [`api/`](api/) — FastAPI backend (Cloud Run). Ports the `lengua_core` domain logic,
  verifies Supabase JWTs, scopes data per user, and is the only thing that talks to the
  LLM provider. Built out in Phase 0 group 0.2 and Phase 1.
- [`web/`](web/) — React + TypeScript app (Vite). The single UI codebase served to web and,
  via Capacitor, to iOS/Android. Built out in Phase 0 group 0.3 and Phase 4.
