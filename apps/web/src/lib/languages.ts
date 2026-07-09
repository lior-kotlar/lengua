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
import { getApiClient, isApiError, unwrap } from '@/lib/api-client';
import { CEFR_BANDS } from '@/lib/cefr';
import { findCurated } from '@/lib/curated-languages';
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

/** Outcome of {@link useAddLanguage}: the language plus how the add resolved. */
export interface AddLanguageResult {
  /** The created or pre-existing language. */
  language: LanguageOut;
  /**
   * `true` when this call CREATED a new language; `false` when the name already existed (idempotent
   * re-add). The backend signals this with a `created` flag on the (200) `POST` response. Re-adding
   * an existing language must NOT reset its proficiency, so the caller skips the starting-band write
   * and tells the user "you already have it".
   */
  created: boolean;
  /**
   * `true` when a NEW language was created with a non-default starting band but the follow-up
   * proficiency `PUT` failed — the language exists (at the default A1 level) and is in the list,
   * but its chosen level wasn't applied. A soft, non-blocking warning rather than a failed add.
   */
  bandError: boolean;
}

/**
 * Create a language, then (only for a brand-new one with a non-default band) set its CEFR level.
 *
 * Reconciliation note: the plan's "add language (name + CEFR starting level)" is split across two
 * endpoints because `POST /languages` accepts only `{name, code, vowelized}` and CEFR is managed via
 * `PUT /proficiency/{id}`. The `POST` response carries a `created` flag (true = a new row was
 * inserted; false = the name already existed), and we branch on that:
 *
 *  - S3 (data-loss guard): on `created: false` (idempotent re-add) we return the existing row
 *    untouched and SKIP the proficiency `PUT`, so re-adding an existing language never resets its
 *    (possibly advanced) CEFR score.
 *  - S12 (atomicity): the list is invalidated on POST success regardless of the band `PUT`; if that
 *    follow-up `PUT` fails we don't fail the whole add — the language was created — we just flag
 *    `bandError` so the caller can warn that only the level wasn't set.
 *
 * The band `PUT` is skipped for the default `A1` (it already maps to the zero starting score).
 */
export function useAddLanguage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: AddLanguageInput): Promise<AddLanguageResult> => {
      const code = input.code?.trim();
      const result = await unwrap(
        getApiClient().POST('/languages', {
          body: {
            name: input.name.trim(),
            code: code !== undefined && code !== '' ? code : null,
            vowelized: input.vowelized ?? false,
          },
        }),
      );
      // The (200) POST response carries a `created` flag; split it off from the language fields so
      // `language` is a plain `LanguageOut` for `onCreated` / the active-language context.
      const { created, ...language } = result;

      let bandError = false;
      if (
        created &&
        input.band !== undefined &&
        input.band !== CEFR_BANDS[0] &&
        (CEFR_BANDS as readonly string[]).includes(input.band)
      ) {
        try {
          await unwrap(
            getApiClient().PUT('/proficiency/{language_id}', {
              params: { path: { language_id: language.id } },
              body: { band: input.band },
            }),
          );
        } catch (error) {
          // The language WAS created; don't reject the whole add (S12). Surface a soft warning and
          // let `onSuccess` still invalidate the list so the new language appears. Re-throw only a
          // non-API (transport/programming) error, which TanStack surfaces via `onError`.
          if (!isApiError(error)) {
            throw error;
          }
          bandError = true;
        }
      }

      return { language, created, bandError };
    },
    onSuccess: ({ language, created }) => {
      // Activation-funnel event (5.9.2): consent-gated, only on an actual create (not a re-add),
      // and only non-PII signals — the language code and whether it's a curated pick (#95), never
      // the display name.
      if (created) {
        trackLanguageAdded(
          language.code ?? null,
          findCurated(language.name) !== undefined,
        );
      }
      // S12: invalidate on POST success regardless of the band PUT outcome, so a freshly created
      // language always shows up in the list (and the panel reflects any level change).
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
