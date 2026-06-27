/**
 * Account-lifecycle data layer (group 4.8) — data export + hard account deletion.
 *
 * Two store-compliance / GDPR endpoints, both deriving the target user solely from the verified JWT
 * (no user-id parameter), so a caller can only ever export or delete THEIR OWN account:
 *
 *  - `GET /account/export` → a JSON bundle of everything the user owns (profile, languages, cards,
 *    reviews, proficiency, settings), offered to the browser as a downloadable file.
 *  - `DELETE /account` → hard-deletes the Supabase auth user (the `auth.users → profiles → domain`
 *    cascade removes all data atomically) and returns `204`. The single irreversible step runs last
 *    server-side, so a partial failure removes nothing and returns a retryable **502**.
 *
 * Everything goes through `getApiClient()` (auth + 401-retry) and `unwrap()` (typed data / typed
 * {@link import('@/lib/api-client').ApiError}); Supabase is auth-only. This module never logs the
 * session token or the export contents.
 */
import { useMutation } from '@tanstack/react-query';
import type { components } from 'api-types';

import { getApiClient, unwrap } from '@/lib/api-client';

/** The full account export bundle returned by `GET /account/export`. */
export type AccountExport = components['schemas']['AccountExport'];

/** Filename offered for the downloaded export (matches the backend's `Content-Disposition`). */
export const ACCOUNT_EXPORT_FILENAME = 'lengua-export.json';

/**
 * The exact phrase the user must type to confirm deletion.
 *
 * Deliberately a deliberate, lowercase sentence (not a single click): the in-dialog delete button
 * stays disabled until the typed text matches this exactly, so an irreversible hard-delete can never
 * be fired by a misclick.
 */
export const DELETE_CONFIRM_PHRASE = 'delete my account';

/**
 * `GET /account/export`: fetch the authenticated user's full data bundle.
 *
 * A mutation (not a query) because it is user-triggered and one-shot — the user clicks "Export", we
 * fetch once and hand the result to {@link downloadJson}. Returns the typed bundle so the caller can
 * download it (or render it) without re-parsing.
 */
export function useExportAccount() {
  return useMutation({
    mutationFn: (): Promise<AccountExport> =>
      unwrap(getApiClient().GET('/account/export')),
  });
}

/**
 * `DELETE /account`: hard-delete the authenticated user's account (irreversible).
 *
 * Resolves to `void` on success (`204`, no body). A partial server-side failure surfaces as a typed
 * `ApiError` with status `502` and a friendly retryable message — the caller keeps the dialog open
 * so the user can retry. Fired EXACTLY ONCE per confirmation by the calling dialog (the button is
 * disabled while pending).
 */
export function useDeleteAccount() {
  return useMutation({
    mutationFn: async (): Promise<void> => {
      await unwrap(getApiClient().DELETE('/account'));
    },
  });
}

/**
 * Offer `data` to the browser as a downloaded, pretty-printed JSON file named `filename`.
 *
 * Serializes to a Blob, creates a temporary object URL, clicks a hidden `<a download>`, then revokes
 * the URL — the standard client-side download with no server round-trip. Kept pure (no React) so it
 * is trivially testable and reusable.
 */
export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
