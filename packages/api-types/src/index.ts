/**
 * Public surface of the generated Lengua API types package.
 *
 * `./schema` is produced by `pnpm --filter api-types generate` (openapi-typescript reading
 * `apps/api/openapi.json`) and is checked in; a CI drift check fails the PR if it is stale.
 * This module re-exports the generated model types and wraps `openapi-fetch` in a small, fully
 * typed client factory so `apps/web` (Phase 4) can call the API with end-to-end type safety.
 */
import createClient, { type ClientOptions } from 'openapi-fetch';

import type { paths } from './schema';

export type { components, operations, paths } from './schema';

/**
 * Create a fully typed fetch client for the Lengua API.
 *
 * Every path, method, request body and response is checked against the committed OpenAPI
 * contract, so a backend change that is not reflected in `openapi.json` surfaces as a type error.
 *
 * @example
 * const api = createApiClient({ baseUrl: 'http://localhost:8000' });
 * const { data, error } = await api.GET('/health');
 */
export function createApiClient(options?: ClientOptions) {
  return createClient<paths>(options);
}
