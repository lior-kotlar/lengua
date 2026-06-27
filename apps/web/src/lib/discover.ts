/**
 * Discover data layer — the `POST /discover` preview mutation plus the pure helpers the Discover
 * screen (group 4.7) builds on. Ported from the legacy Streamlit Discover page.
 *
 * The flow: pick a count (+ optional topic) → `POST /discover` returns new vocabulary words the
 * learner does not already know (a preview, nothing persisted) → accept them (handed off into the
 * Generate flow, group 4.5) or reroll for a fresh set. Generation/quota live on the Generate side;
 * Discover only previews words. Everything goes through `getApiClient()` (auth + 401-retry) and
 * `unwrap()` (typed data / typed {@link import('@/lib/api-client').ApiError}); Supabase is auth-only.
 */
import { useMutation } from '@tanstack/react-query';
import { schemaLimits } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';
import { DISCOVER_COUNT_KEY, type SettingsOut } from '@/lib/settings';

/**
 * Bounds + default for the request count, read from the OpenAPI contract
 * (`DiscoverRequest.count` minimum/maximum/default) rather than hard-coded — so the client always
 * matches the server. The form clamps to `[MIN, MAX]` (the server 422s outside it) and falls back to
 * `DEFAULT` when the user has no saved preference.
 */
export const DISCOVER_COUNT_MIN = schemaLimits.discoverCountMin;
export const DISCOVER_COUNT_MAX = schemaLimits.discoverCountMax;
export const DISCOVER_COUNT_DEFAULT = schemaLimits.discoverCountDefault;

/**
 * Clamp a count into the request bounds, rounding to a whole number; a non-finite value falls back
 * to the server default. Keeps Discover from ever sending a count the server would reject (422).
 */
export function clampDiscoverCount(value: number): number {
  if (!Number.isFinite(value)) {
    return DISCOVER_COUNT_DEFAULT;
  }
  const rounded = Math.round(value);
  return Math.min(DISCOVER_COUNT_MAX, Math.max(DISCOVER_COUNT_MIN, rounded));
}

/**
 * The default word count for the Discover form: the user's saved `discover_count` setting (clamped
 * to the request bounds), or the server's own default when it is unset/blank/non-numeric. This is
 * what makes the form "default to the user's discover-count setting" (task 4.7.1).
 */
export function resolveDiscoverCount(
  settings: SettingsOut | undefined,
): number {
  const raw = settings?.values[DISCOVER_COUNT_KEY];
  if (raw === undefined || raw === null || raw.trim() === '') {
    return DISCOVER_COUNT_DEFAULT;
  }
  return clampDiscoverCount(Number(raw));
}

/** Input to {@link useDiscover}. `topic` is `null` when the optional topic field is left blank. */
export interface DiscoverInput {
  languageId: number;
  count: number;
  topic: string | null;
}

/**
 * `POST /discover`: preview up to `count` new words for the active language (nothing persisted).
 *
 * Returns just the suggested word list (the screen only needs the words). A repeat with the same
 * `(language, topic, count)` may be served from the backend's short-window reuse cache — so a
 * "reroll" with identical inputs can legitimately return the same set; the screen still refetches
 * and replaces whatever comes back.
 */
export function useDiscover() {
  return useMutation({
    mutationFn: (input: DiscoverInput): Promise<string[]> =>
      unwrap(
        getApiClient().POST('/discover', {
          body: {
            language_id: input.languageId,
            count: input.count,
            topic: input.topic,
          },
        }),
      ).then((response) => response.words),
  });
}
