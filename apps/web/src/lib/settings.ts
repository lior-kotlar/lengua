/**
 * Settings data layer — the user's key/value preferences map (`GET` / `PUT /settings`).
 *
 * The backend keeps a small, generic `{ key: value }` store (daily review limits, the Discover
 * default word count, …) rather than a fixed schema, so new preferences need no migration. This
 * module exposes the read query, the upsert mutation, and the editable-field model the Settings
 * screen (group 4.8) drives — plus the pure bounds validation that keeps a saved value inside what
 * the server expects. Everything goes through `getApiClient()` (auth + 401-retry) and `unwrap()`
 * (typed data / typed {@link import('@/lib/api-client').ApiError}); Supabase is auth-only.
 *
 * **Server bounds (provenance).** `PUT /settings` itself accepts any string value (it is a generic
 * store), so the bounds the UI validates against come from where each key is actually consumed:
 *
 *  - `discover_count` has a REAL server-enforced bound — `POST /discover` rejects a count outside
 *    `DiscoverRequest.count` minimum/maximum with **422**. We read that bound from the OpenAPI
 *    contract (`schemaLimits.discoverCount{Min,Max,Default}`, emitted by `pnpm gen:api` and
 *    drift-checked in CI) so the client always matches the server — never hard-coded.
 *  - `daily_new_limit` / `daily_total_limit` are the review-batch limits. The generic settings store
 *    enforces no numeric bound on them today (and the review router still uses the `lengua_core`
 *    config defaults — wiring the per-user keys into the due batch is a tracked backend gap), so we
 *    validate against the sane product bounds the legacy Streamlit settings page used (new 1–100,
 *    total 1–500). They are documented as client-side product bounds, not schema-enforced ones.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { schemaLimits, type components } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';

/** The user's settings as a `{ key: value }` map (`GET /settings`). */
export type SettingsOut = components['schemas']['SettingsOut'];

/**
 * Known setting keys. Generic string keys in the backend's preferences map (so a new preference
 * needs no migration); named here so Discover, the Settings screen, and the backend agree on them.
 */
/** How many new words Discover suggests by default. */
export const DISCOVER_COUNT_KEY = 'discover_count';
/** Max brand-new (never-reviewed) cards shown in one review session. */
export const DAILY_NEW_LIMIT_KEY = 'daily_new_limit';
/** Hard cap on the total cards (new + due) in one review session. */
export const DAILY_TOTAL_LIMIT_KEY = 'daily_total_limit';

/** Query key for the user's settings map. */
export function settingsKey() {
  return ['settings'] as const;
}

/**
 * Fetch the user's settings map (`GET /settings`).
 *
 * Not language-scoped (settings are per user, not per language), so the key carries no language id.
 * Used by Discover for its default word count and by the Settings screen for the editable fields.
 */
export function useSettingsQuery() {
  return useQuery({
    queryKey: settingsKey(),
    queryFn: () => unwrap(getApiClient().GET('/settings')),
  });
}

/**
 * Upsert (merge) one or more settings (`PUT /settings`).
 *
 * The backend merges the supplied keys into the user's map and returns the full updated map, which
 * we write straight into the query cache with `setQueryData` — authoritative and refetch-free, so
 * Discover's `useSettingsQuery` immediately reflects a new `discover_count` without another GET.
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, string>): Promise<SettingsOut> =>
      unwrap(getApiClient().PUT('/settings', { body: { values } })),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKey(), data);
    },
  });
}

/** An editable, integer-valued setting on the Settings screen. */
export interface SettingsFieldDef {
  /** The backend settings key. */
  key: string;
  /** Field label (also the input's accessible name). */
  label: string;
  /** Help text shown under the input. */
  description: string;
  /** Inclusive minimum accepted value. */
  min: number;
  /** Inclusive maximum accepted value. */
  max: number;
  /** Value shown when the user has no saved preference for this key. */
  fallback: number;
}

/**
 * The editable settings, in display order: the two review limits + the Discover default count.
 *
 * `discover_count`'s bounds come from the OpenAPI schema (the server 422s outside them); the daily
 * review limits use the legacy app's product bounds (see the module docstring for provenance).
 */
export const SETTINGS_FIELDS: readonly SettingsFieldDef[] = [
  {
    key: DAILY_NEW_LIMIT_KEY,
    label: 'Daily new cards',
    description: 'Most brand-new cards shown in a single review session.',
    min: 1,
    max: 100,
    fallback: 10,
  },
  {
    key: DAILY_TOTAL_LIMIT_KEY,
    label: 'Daily total cards',
    description: 'Cap on the total cards (new + due) in one review session.',
    min: 1,
    max: 500,
    fallback: 50,
  },
  {
    key: DISCOVER_COUNT_KEY,
    label: 'Discover word count',
    description: 'How many new words Discover suggests by default.',
    min: schemaLimits.discoverCountMin,
    max: schemaLimits.discoverCountMax,
    fallback: schemaLimits.discoverCountDefault,
  },
];

/**
 * Validate a raw input value for `field`, returning an inline error message or `null` when valid.
 *
 * Rejects anything that is not a whole number within `[min, max]` — so the form blocks (and never
 * sends) a value the server would reject (`discover_count`) or that makes no sense for a review
 * limit. Used both to gate the Save button and to show the per-field message.
 */
export function validateSettingValue(
  field: SettingsFieldDef,
  raw: string,
): string | null {
  const trimmed = raw.trim();
  if (trimmed === '') {
    return 'Enter a value.';
  }
  if (!/^\d+$/.test(trimmed)) {
    return 'Enter a whole number.';
  }
  const value = Number(trimmed);
  if (value < field.min || value > field.max) {
    return `Must be between ${field.min} and ${field.max}.`;
  }
  return null;
}

/**
 * The form's initial string value for `field`: the user's saved value when present and non-blank,
 * otherwise the field's fallback default (so the input always shows the effective value).
 */
export function initialSettingValue(
  settings: SettingsOut | undefined,
  field: SettingsFieldDef,
): string {
  const raw = settings?.values[field.key];
  if (raw === undefined || raw === null || raw.trim() === '') {
    return String(field.fallback);
  }
  return raw.trim();
}
