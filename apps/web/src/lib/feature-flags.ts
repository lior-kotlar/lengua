/**
 * Feature flags (web side) — read the server-resolved flag map from the API (task 6.9.1).
 *
 * The backend owns flag resolution (env defaults overlaid by the global `feature_flags` table,
 * cached for a short TTL). The web simply reads the resolved PUBLIC map from the public, secret-free
 * `GET /feature-flags` endpoint and uses it to gate dark UI. Because the value lives server-side, an
 * operator can flip a flag in prod and the web reflects it on the next refetch — no web redeploy.
 *
 * Everything goes through `getApiClient()` + `unwrap()` (typed data / typed
 * {@link import('@/lib/api-client').ApiError}); the endpoint needs no auth, so it works before/without
 * a session. Resolution fails SAFE: while loading or on error a flag reads as `false`, so a gated
 * feature stays dark rather than flashing on.
 */
import { useQuery } from '@tanstack/react-query';

import { getApiClient, unwrap } from '@/lib/api-client';

/** The resolved public flag map: `{ flagName: enabled }`. */
export type FeatureFlagMap = Record<string, boolean>;

/** The experimental "word of the day" flag — ships dark (off by default). Matches the backend name. */
export const WORD_OF_THE_DAY_FLAG = 'word_of_the_day';

/** Query key for the feature-flag map. */
export function featureFlagsKey() {
  return ['feature-flags'] as const;
}

/**
 * Fetch the resolved PUBLIC feature-flag map (`GET /feature-flags`).
 *
 * `staleTime` keeps it from refetching on every mount (the backend already caches), while still
 * picking up a prod toggle on the next natural refetch — so a flag change reaches the browser
 * without a web redeploy.
 */
export function useFeatureFlagsQuery() {
  return useQuery({
    queryKey: featureFlagsKey(),
    queryFn: () => unwrap(getApiClient().GET('/feature-flags')),
    staleTime: 30_000,
  });
}

/**
 * Read a single flag's resolved state (defaulting to `false`).
 *
 * Returns `false` while the map is loading or if the request failed, so a gated feature is never
 * shown until the server confirms it is on.
 */
export function useFeatureFlag(name: string): boolean {
  const { data } = useFeatureFlagsQuery();
  return data?.[name] ?? false;
}
