# packages

Shared packages used across the apps, part of the root pnpm workspace
(`pnpm-workspace.yaml`).

- **[`api-types/`](api-types/)** — the OpenAPI-generated TypeScript types + a typed client for
  the Lengua API, derived from `apps/api/openapi.json`. Generated code; excluded from the web
  app's lint/coverage scopes. Regenerate with `pnpm --filter api-types generate`.
