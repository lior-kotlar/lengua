/**
 * Languages data layer — TanStack Query hooks over the typed API client (group 4.4).
 *
 * Every call goes through `getApiClient()` (auth + 401-retry) and `unwrap()` (typed data / typed
 * `ApiError`). The query key (`['languages']`) is shared so a create/remove can invalidate the list
 * from anywhere, and screens that scope by language read it from here rather than refetching ad hoc.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from 'api-types';

import { trackLanguageAdded } from '@/lib/analytics-events';
import { getApiClient, unwrap } from '@/lib/api-client';
import { CEFR_BANDS } from '@/lib/cefr';
import { proficiencyKey } from '@/lib/proficiency';

/** A language as returned by the API (`GET /languages`). */
export type LanguageOut = components['schemas']['LanguageOut'];

/**
 * A minimal placeholder language for the defensive case where a language id is selected but its
 * full object hasn't resolved yet (e.g. mid-load): LTR, no script font, not vowelized — so a
 * language-scoped screen renders sensibly instead of crashing on a missing object.
 */
export function fallbackLanguage(id: number): LanguageOut {
  return { id, name: '', code: null, vowelized: false };
}

/** Query key for the current user's language list. */
export const languagesKey = ['languages'] as const;

/** Fetch the current user's languages (oldest first), scoped to the JWT by the backend. */
export function useLanguagesQuery() {
  return useQuery({
    queryKey: languagesKey,
    queryFn: () => unwrap(getApiClient().GET('/languages')),
  });
}

/** Input to {@link useAddLanguage}: the create fields plus an optional CEFR starting band. */
export interface AddLanguageInput {
  /** Display name, e.g. "Spanish" (required). */
  name: string;
  /** Optional ISO-ish language code, e.g. "es" (also drives text direction later, group 4.9). */
  code?: string;
  /** Whether to request fully vocalized output (harakat / nikkud) for this language. */
  vowelized?: boolean;
  /**
   * Optional starting CEFR band. The create endpoint takes name/code/vowelized ONLY — CEFR lives in
   * proficiency — so a non-default starting band is applied with a follow-up `PUT /proficiency`.
   */
  band?: string;
}

/**
 * Create a language, then (if a non-default starting band was chosen) set its CEFR level.
 *
 * Reconciliation note: the plan's "add language (name + CEFR starting level)" is split across two
 * endpoints because `POST /languages` accepts only `{name, code, vowelized}` and CEFR is managed via
 * `PUT /proficiency/{id}`. We create first, then PUT the band only when it differs from the default
 * `A1` (which already maps to the zero starting score, so a PUT would be a no-op). On success the
 * language list — and the new language's proficiency — are invalidated so every screen sees it.
 */
export function useAddLanguage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: AddLanguageInput): Promise<LanguageOut> => {
      const code = input.code?.trim();
      const language = await unwrap(
        getApiClient().POST('/languages', {
          body: {
            name: input.name.trim(),
            code: code !== undefined && code !== '' ? code : null,
            vowelized: input.vowelized ?? false,
          },
        }),
      );

      if (
        input.band !== undefined &&
        input.band !== CEFR_BANDS[0] &&
        (CEFR_BANDS as readonly string[]).includes(input.band)
      ) {
        await unwrap(
          getApiClient().PUT('/proficiency/{language_id}', {
            params: { path: { language_id: language.id } },
            body: { band: input.band },
          }),
        );
      }

      return language;
    },
    onSuccess: (language) => {
      // Activation-funnel event (5.9.2): consent-gated, only the (non-PII) language code.
      trackLanguageAdded(language.code ?? null);
      void queryClient.invalidateQueries({ queryKey: languagesKey });
      void queryClient.invalidateQueries({
        queryKey: proficiencyKey(language.id),
      });
    },
  });
}

/** Delete a language (its cards + proficiency cascade on the server). Invalidates the list. */
export function useRemoveLanguage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (languageId: number) =>
      unwrap(
        getApiClient().DELETE('/languages/{language_id}', {
          params: { path: { language_id: languageId } },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: languagesKey });
    },
  });
}
