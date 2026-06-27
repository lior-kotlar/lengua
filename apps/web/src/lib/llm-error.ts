/**
 * Shared classification of the backend cost-guard error states (group 4.5; reused by Discover 4.7
 * and any future LLM-bound call per the cross-cutting 429 contract).
 *
 * Every LLM-bound endpoint (`/generate`, `/discover`, ...) can fail with one of the cost-guard
 * shapes the backend documents — surfaced by the typed {@link ApiError} as an HTTP status + a
 * machine `code`. Screens must render FRIENDLY, ACTIONABLE states for these instead of a raw error,
 * and the "daily limit reached" case in particular gets a dedicated, shared panel
 * ({@link import('@/components/daily-limit-panel').DailyLimitPanel}). This module is the single
 * source of truth for mapping an unknown caught value to one of those states, so Generate and
 * Discover classify identically.
 */
import { ApiError, isApiError } from '@/lib/api-client';

/**
 * The friendly states an LLM-bound call can resolve to on failure:
 * - `daily_limit` — the per-user daily cap (`daily_cap_reached`) or the global kill-switch
 *   (`daily_limit_reached`); both render the shared "try again tomorrow" panel.
 * - `rate_limited` — too many requests in a short window (has a `Retry-After`).
 * - `server_busy` — the concurrency cap / a transient upstream 5xx (has a `Retry-After`).
 * - `email_unverified` — the account must verify its email before generating.
 * - `generic` — anything else (network failure, 404, 500, ...): a plain retryable error.
 */
export type LlmErrorKind =
  | 'daily_limit'
  | 'rate_limited'
  | 'server_busy'
  | 'email_unverified'
  | 'generic';

/**
 * True for the quota-429 "daily limit" shape — the per-user daily cap (`daily_cap_reached`) or the
 * global daily kill-switch (`daily_limit_reached`). This is the exact shape the shared
 * {@link import('@/components/daily-limit-panel').DailyLimitPanel} is tied to; both Generate and
 * Discover branch on it to show the panel rather than a generic error.
 */
export function isDailyLimitError(error: unknown): error is ApiError {
  return (
    isApiError(error) &&
    error.status === 429 &&
    (error.code === 'daily_cap_reached' || error.code === 'daily_limit_reached')
  );
}

/** Map any caught value from an LLM-bound call to one of the {@link LlmErrorKind} states. */
export function classifyLlmError(error: unknown): LlmErrorKind {
  if (isDailyLimitError(error)) {
    return 'daily_limit';
  }
  if (isApiError(error)) {
    if (error.code === 'rate_limited') {
      return 'rate_limited';
    }
    if (error.code === 'server_busy') {
      return 'server_busy';
    }
    if (error.code === 'email_unverified') {
      return 'email_unverified';
    }
  }
  return 'generic';
}

/** A friendly, user-facing title + body for an error state. */
export interface LlmErrorDescription {
  title: string;
  description: string;
}

/** Phrase a `Retry-After` delay (seconds) as a friendly "try again in N seconds" clause. */
function retryClause(retryAfter: number | undefined): string {
  if (retryAfter !== undefined && retryAfter > 0) {
    const unit = retryAfter === 1 ? 'second' : 'seconds';
    return `Please try again in ${retryAfter} ${unit}.`;
  }
  return 'Please try again in a moment.';
}

/**
 * A friendly {@link LlmErrorDescription} for the NON-daily-limit states (the daily-limit case has
 * its own dedicated panel, but is handled here too so the mapping is total). Used to render the
 * inline error/transient states on Generate (and Discover) without leaking raw error text.
 */
export function describeLlmError(error: unknown): LlmErrorDescription {
  const retryAfter = isApiError(error) ? error.retryAfter : undefined;
  switch (classifyLlmError(error)) {
    case 'daily_limit':
      return {
        title: 'Daily limit reached',
        description:
          'You have reached the daily limit. Please try again tomorrow.',
      };
    case 'rate_limited':
      return {
        title: 'Too many requests',
        description: `You are going a little fast. ${retryClause(retryAfter)}`,
      };
    case 'server_busy':
      return {
        title: 'The server is busy',
        description: `We are handling a lot of requests right now. ${retryClause(retryAfter)}`,
      };
    case 'email_unverified':
      return {
        title: 'Verify your email',
        description:
          'Please verify your email address before generating sentences.',
      };
    default:
      return {
        title: 'Something went wrong',
        description: isApiError(error) ? error.message : 'Please try again.',
      };
  }
}
