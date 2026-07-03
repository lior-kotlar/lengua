/**
 * Proficiency data layer — TanStack Query hooks over the typed API client (group 4.4).
 *
 * `GET /proficiency/{language_id}` returns the learner's level (continuous `score`, CEFR `band`, and
 * intra-band `progress`); `PUT` overrides it by band (a manual CEFR override that re-levels future
 * generation). Keyed per language so switching the active language naturally refetches.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';

/** A learner's level for one language (`GET /proficiency/{language_id}`). */
export type ProficiencyOut = components['schemas']['ProficiencyOut'];

/** Query key for one language's proficiency. */
export function proficiencyKey(languageId: number) {
  return ['proficiency', languageId] as const;
}

/**
 * Fetch a language's proficiency (`GET /proficiency/{language_id}`) — the shared fetcher behind both
 * {@link useProficiencyQuery} (the CEFR panel) and the Dashboard's per-language fan-out
 * ({@link import('@/lib/dashboard').useDashboardTiles}), so the level for a language is fetched under
 * the one {@link proficiencyKey} cache entry rather than requested twice.
 *
 * The id is always concrete here (callers gate on `null` themselves); the shared cache key is
 * {@link proficiencyKey}.
 */
export function fetchProficiency(languageId: number): Promise<ProficiencyOut> {
  return unwrap(
    getApiClient().GET('/proficiency/{language_id}', {
      params: { path: { language_id: languageId } },
    }),
  );
}

/**
 * Fetch the active language's proficiency.
 *
 * `languageId` may be `null` (no language selected yet); the query is disabled until one exists, so
 * the panel renders a neutral "pick a language" state rather than firing a request for `null`.
 */
export function useProficiencyQuery(languageId: number | null) {
  return useQuery({
    queryKey: proficiencyKey(languageId ?? -1),
    queryFn: () => fetchProficiency(languageId as number),
    enabled: languageId !== null,
  });
}

/**
 * Manually override a language's CEFR band (`PUT /proficiency/{language_id}` with `{ band }`).
 *
 * On success the language's proficiency query is invalidated so the level panel reflects the new
 * band immediately (and subsequent generation uses the new level).
 */
export function useSetProficiencyBand(languageId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (band: string): Promise<ProficiencyOut> =>
      unwrap(
        getApiClient().PUT('/proficiency/{language_id}', {
          params: { path: { language_id: languageId } },
          body: { band },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: proficiencyKey(languageId),
      });
    },
  });
}
