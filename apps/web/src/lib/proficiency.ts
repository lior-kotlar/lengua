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
 * Fetch the active language's proficiency.
 *
 * `languageId` may be `null` (no language selected yet); the query is disabled until one exists, so
 * the panel renders a neutral "pick a language" state rather than firing a request for `null`.
 */
export function useProficiencyQuery(languageId: number | null) {
  return useQuery({
    queryKey: proficiencyKey(languageId ?? -1),
    queryFn: () =>
      unwrap(
        getApiClient().GET('/proficiency/{language_id}', {
          params: { path: { language_id: languageId as number } },
        }),
      ),
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
