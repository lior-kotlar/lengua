# api-types

Generated TypeScript types **and** a typed client for the Lengua API. The single source of truth
is the backend's OpenAPI contract, `apps/api/openapi.json` (produced by
`python apps/api/scripts/dump_openapi.py`).

This package is part of the pnpm workspace (`pnpm-workspace.yaml`). It is **generated code** and
is intentionally excluded from the web app's ESLint, Prettier, and vitest coverage scopes.

## Scripts

```bash
# Re-derive src/schema.ts from apps/api/openapi.json (run after the contract changes).
pnpm --filter api-types generate

# Typecheck the generated types + the client wrapper.
pnpm --filter api-types build      # tsc --noEmit
```

CI fails the PR if `src/schema.ts` is stale versus the committed `openapi.json` (a `git diff`
drift check), and a separate backend test (`tests/test_openapi_stable.py`) fails if
`openapi.json` itself is stale versus the live FastAPI schema. So the chain
**app routes → `openapi.json` → `src/schema.ts`** is kept in lockstep.

## Usage (from `apps/web`, Phase 4+)

```ts
import { createApiClient, type components } from 'api-types';

const api = createApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL });
const { data, error } = await api.GET('/review/due', {
  params: { query: { language_id: 1 } },
});

type CardOut = components['schemas']['CardOut'];
```

## Layout

- `src/schema.ts` — **generated** (do not edit by hand) by `openapi-typescript`.
- `src/index.ts` — re-exports the generated `paths` / `components` / `operations` types and the
  `createApiClient` factory (a typed `openapi-fetch` client).
