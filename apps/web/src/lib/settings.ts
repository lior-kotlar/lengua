/**
 * Settings data layer — the user's key/value preferences map (`GET /settings`).
 *
 * The backend keeps a small, generic `{ key: value }` store (daily review limits, the Discover
 * default word count, …) rather than a fixed schema. Today only the Discover screen (group 4.7)
 * reads it — for its default word count — so this module exposes just the read query + the known
 * key; the full Settings editor (group 4.8) will extend it with the upsert mutation + bounds
 * validation. Everything goes through `getApiClient()` (auth + 401-retry) and `unwrap()` (typed
 * data / typed {@link import('@/lib/api-client').ApiError}); Supabase is auth-only.
 */
import { useQuery } from '@tanstack/react-query';
import type { components } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';

/** The user's settings as a `{ key: value }` map (`GET /settings`). */
export type SettingsOut = components['schemas']['SettingsOut'];

/**
 * Known setting key: how many new words Discover suggests by default. A generic string key in the
 * backend's preferences map (so a new preference needs no migration); named here so Discover and
 * the future Settings screen agree on it.
 */
export const DISCOVER_COUNT_KEY = 'discover_count';

/** Query key for the user's settings map. */
export function settingsKey() {
  return ['settings'] as const;
}

/**
 * Fetch the user's settings map (`GET /settings`).
 *
 * Not language-scoped (settings are per user, not per language), so the key carries no language id.
 * Used by Discover for its default word count; the Settings screen (4.8) will reuse this query.
 */
export function useSettingsQuery() {
  return useQuery({
    queryKey: settingsKey(),
    queryFn: () => unwrap(getApiClient().GET('/settings')),
  });
}
