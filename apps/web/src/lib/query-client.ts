/**
 * TanStack Query client factory.
 *
 * Centralized defaults so every screen shares the same caching/retry behavior:
 * - `staleTime` 30s: language/proficiency/settings data doesn't change every render.
 * - `retry` 1 for queries: tolerate a transient blip without hammering the quota-bounded backend
 *   (auth 401s are handled by the dedicated refresh/retry interceptor in a later group, not here).
 * - `retry` 0 for mutations: never silently re-POST a generate/save/grade.
 * - `refetchOnWindowFocus` off: avoids surprise LLM-bound refetches when tabbing back.
 */
import { QueryClient } from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
