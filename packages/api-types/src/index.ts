/**
 * Public surface of the generated Lengua API types package.
 *
 * `./schema` is produced by `pnpm gen:api` (root) / `pnpm --filter api-types generate`
 * (openapi-typescript reading `apps/api/openapi.json`) and is checked in; a CI drift check fails
 * the PR if it is stale. This module re-exports the generated model types and wraps `openapi-fetch`
 * in a small, fully typed client factory so `apps/web` (Phase 4) can call the API with end-to-end
 * type safety — importing everything (models, the client factory, and the `openapi-fetch` helper
 * types) from this single package rather than reaching into `openapi-fetch` directly.
 */
import createClient, { type Client } from 'openapi-fetch';

import type { paths } from './schema';

export type { components, operations, paths } from './schema';
export type { ClientOptions, Middleware } from 'openapi-fetch';

// Runtime schema constants (numeric OpenAPI constraints the generated types can't carry).
// Generated alongside `schema.ts` by `pnpm gen:api`; see `./constants`.
export { schemaLimits } from './constants';

/**
 * A fully typed Lengua API client.
 *
 * Every path, method, request body and response is checked against the committed OpenAPI contract,
 * so a backend change not reflected in `openapi.json` (and thus `schema.ts`) surfaces as a type
 * error in the consuming app.
 */
export type ApiClient = Client<paths>;

/**
 * Create a fully typed fetch client for the Lengua API.
 *
 * @example
 * const api = createApiClient({ baseUrl: 'http://localhost:8000' });
 * const { data, error } = await api.GET('/health');
 */
export function createApiClient(
  options?: Parameters<typeof createClient>[0],
): ApiClient {
  return createClient<paths>(options);
}
