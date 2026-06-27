/**
 * Typed API client — the single seam between the web app and the FastAPI backend.
 *
 * Everything is built on the OpenAPI-generated `api-types` client (`openapi-fetch`), so every
 * path, method, body and response is checked against the committed contract. This module adds the
 * two app-wide concerns on top of that:
 *
 *  1. **Auth.** A request middleware injects `Authorization: Bearer <token>` from the CURRENT
 *     Supabase session on every call. The token is read fresh per request (never cached here), so
 *     when supabase-js refreshes in the background — or the dedicated on-401 refresh/retry
 *     interceptor lands (task 4.3.7) — subsequent requests automatically carry the new token. This
 *     layer never logs or persists the token. Supabase is AUTH ONLY; all data goes through here.
 *
 *  2. **Typed errors.** `unwrap()` turns the `openapi-fetch` `{ data, error, response }` result
 *     into "return typed data on 2xx, throw an {@link ApiError} otherwise" — the ergonomic shape
 *     for TanStack Query. The `ApiError` exposes `{ status, code, message, retryAfter }` parsed
 *     from the body + headers, which is exactly what the backend cost-guard states need downstream
 *     (`email_unverified` / `rate_limited` / `daily_cap_reached` / `daily_limit_reached` /
 *     `server_busy`); the raw parsed `body` is kept too (e.g. for `daily_cap_reached`'s `kind`).
 *
 * Screens normally call `unwrap(getApiClient().GET('/me'))`; the raw `getApiClient()` is the escape
 * hatch when a screen needs the `Response` itself (headers, 204s, file downloads).
 */
import {
  createApiClient,
  type ApiClient,
  type ClientOptions,
  type Middleware,
} from 'api-types';

import { readEnv } from '@/lib/env';
import { getSupabaseClient } from '@/lib/supabase';

export type { ApiClient } from 'api-types';

/**
 * The app-level error `code`s the backend cost guard returns (HTTP status + JSON `code`). These
 * are app-level handlers, not part of the OpenAPI schema, so they are modelled here by hand. The
 * `ApiError.code` field is a plain `string` (the backend may add codes, e.g. FastAPI's own); this
 * union documents the ones the UI surfaces as friendly, actionable states.
 */
export type ApiErrorCode =
  | 'email_unverified'
  | 'rate_limited'
  | 'daily_cap_reached'
  | 'daily_limit_reached'
  | 'server_busy';

/** Fields used to construct an {@link ApiError}. */
export interface ApiErrorInit {
  /** HTTP status code (0 for a transport/network failure with no response). */
  status: number;
  /** Human-readable message (a sensible default is derived if the body has none). */
  message: string;
  /** Machine-readable code from the response body, when present (see {@link ApiErrorCode}). */
  code?: string;
  /** Seconds to wait before retrying, parsed from the `Retry-After` header, when present. */
  retryAfter?: number;
  /** The raw parsed response body, for any extra fields (e.g. `daily_cap_reached`'s `kind`). */
  body?: unknown;
  /** The underlying cause (e.g. the thrown transport error). */
  cause?: unknown;
}

/**
 * A typed error for any non-2xx API response (or a transport failure).
 *
 * Carries the cost-guard contract `{ status, code, message, retryAfter }` so screens can render the
 * right friendly state instead of a generic error.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryAfter?: number;
  readonly body: unknown;

  constructor(init: ApiErrorInit) {
    super(
      init.message,
      init.cause !== undefined ? { cause: init.cause } : undefined,
    );
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.retryAfter = init.retryAfter;
    this.body = init.body;
  }
}

/** Type guard: narrow an unknown caught value to {@link ApiError}. */
export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Parse the `Retry-After` header (delta-seconds) into a non-negative number, or `undefined`. */
function parseRetryAfter(response: Response): number | undefined {
  const header = response.headers.get('Retry-After');
  if (header === null || header.trim() === '') {
    return undefined;
  }
  const seconds = Number.parseInt(header, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined;
}

/**
 * Build an {@link ApiError} from a non-2xx response and its already-parsed body.
 *
 * `openapi-fetch` parses the body for us (JSON by default), so we read `code`/`message` from it
 * here rather than re-reading the (already-consumed) response stream. Falls back to FastAPI's
 * `detail` string, then to a generic status message.
 */
export function toApiError(response: Response, body: unknown): ApiError {
  let code: string | undefined;
  let message: string | undefined;

  if (body !== null && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.code === 'string') {
      code = record.code;
    }
    if (typeof record.message === 'string') {
      message = record.message;
    } else if (typeof record.detail === 'string') {
      message = record.detail;
    }
  }

  return new ApiError({
    status: response.status,
    code,
    message: message ?? `Request failed with status ${response.status}`,
    retryAfter: parseRetryAfter(response),
    body,
  });
}

/** The shape every `openapi-fetch` call resolves to; `unwrap` narrows it to the success data. */
interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/**
 * Await an `openapi-fetch` call and return its typed success data, or throw an {@link ApiError}.
 *
 * - 2xx → resolves with the typed `data` (`undefined` for empty bodies such as 204).
 * - non-2xx → throws {@link ApiError} with the parsed cost-guard fields.
 * - transport failure (no response) → throws {@link ApiError} with `status: 0`.
 *
 * @example
 * const me = await unwrap(getApiClient().GET('/me'));
 */
export async function unwrap<T>(call: Promise<ApiResult<T>>): Promise<T> {
  let result: ApiResult<T>;
  try {
    result = await call;
  } catch (cause) {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message:
        cause instanceof Error ? cause.message : 'Network request failed',
      cause,
    });
  }

  const { data, error, response } = result;
  if (!response.ok) {
    throw toApiError(response, error);
  }
  return data as T;
}

/** Read the access token from the current Supabase session (the default token source). */
async function sessionAccessToken(): Promise<string | null> {
  const { data } = await getSupabaseClient().auth.getSession();
  return data.session?.access_token ?? null;
}

// ── Central token refresh + 401 retry (task 4.3.7) ──────────────────────────────────────────────
//
// supabase-js refreshes the access token in the background, but a token can still expire in the
// window between a request being built and the server validating it. So on a 401 we refresh ONCE
// via supabase-js and retry the request with the new token; if the refresh itself fails we sign out
// (which clears the Query cache via the AuthProvider and lets the route guard redirect to /login).

/**
 * In-flight refresh promise, so a burst of concurrent 401s triggers exactly ONE `refreshSession()`
 * (no refresh storm). Reset once it settles. The returned token is only ever written to a request
 * header — never logged or persisted here.
 */
let inFlightRefresh: Promise<string | null> | null = null;

/** Refresh the Supabase session once (deduped) and return the new access token, or null on failure. */
async function sessionRefreshToken(): Promise<string | null> {
  if (inFlightRefresh === null) {
    inFlightRefresh = (async () => {
      try {
        const { data, error } = await getSupabaseClient().auth.refreshSession();
        if (error !== null) {
          return null;
        }
        return data.session?.access_token ?? null;
      } catch {
        return null;
      }
    })();
    void inFlightRefresh.finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

/** Default refresh-failure handler: sign out (AuthProvider then clears the cache + guard redirects). */
async function defaultOnAuthFailure(): Promise<void> {
  await getSupabaseClient().auth.signOut();
}

/** The single-argument `(Request) => Promise<Response>` fetch shape `openapi-fetch` calls. */
type FetchImpl = (request: Request) => Promise<Response>;

/**
 * Wrap a fetch so that a 401 triggers a one-time token refresh + retry.
 *
 * The request is cloned BEFORE the first send (a sent body can't be re-read), so the retry can be
 * re-issued with the refreshed `Authorization`. There is at most ONE retry (no loop): if the retried
 * request also 401s, that response is returned as-is. If the refresh fails, `onAuthFailure` runs and
 * the original 401 is surfaced.
 */
export function createRefreshRetryFetch(
  baseFetch: FetchImpl,
  refreshAccessToken: () => Promise<string | null>,
  onAuthFailure: () => void | Promise<void>,
): FetchImpl {
  return async (request) => {
    const retryRequest = request.clone();
    const response = await baseFetch(request);
    if (response.status !== 401) {
      return response;
    }

    const token = await refreshAccessToken();
    if (token === null) {
      await onAuthFailure();
      return response;
    }

    retryRequest.headers.set('Authorization', `Bearer ${token}`);
    return baseFetch(retryRequest);
  };
}

/** Middleware that attaches `Authorization: Bearer <token>` when a session token is available. */
function authMiddleware(
  getAccessToken: () => Promise<string | null>,
): Middleware {
  return {
    async onRequest({ request }) {
      const token = await getAccessToken();
      if (token !== null && token !== '') {
        request.headers.set('Authorization', `Bearer ${token}`);
      }
      return request;
    },
  };
}

/** Options for {@link createAuthedApiClient}; all default to the production wiring. */
export interface AuthedApiClientOptions {
  /** API base URL (defaults to `VITE_API_BASE_URL` via `readEnv()`). */
  baseUrl?: string;
  /** Custom fetch implementation (used in tests to capture requests / return canned responses). */
  fetch?: ClientOptions['fetch'];
  /** Access-token source (defaults to the current Supabase session). */
  getAccessToken?: () => Promise<string | null>;
  /** Refresh the session + return a fresh access token (defaults to supabase-js `refreshSession`). */
  refreshAccessToken?: () => Promise<string | null>;
  /** Invoked when a refresh fails (defaults to signing out the Supabase session). */
  onAuthFailure?: () => void | Promise<void>;
}

/**
 * Create a typed API client with the auth + refresh/retry layers attached.
 *
 * Exposed (vs. just the singleton) so tests can inject a base URL, a fetch, a token source, and the
 * refresh/auth-failure hooks. The request middleware injects the current bearer token; the fetch
 * wrapper handles the 401 → refresh-once → retry path (task 4.3.7).
 */
export function createAuthedApiClient(
  options: AuthedApiClientOptions = {},
): ApiClient {
  const baseUrl = options.baseUrl ?? readEnv().apiBaseUrl;
  const getAccessToken = options.getAccessToken ?? sessionAccessToken;
  const refreshAccessToken = options.refreshAccessToken ?? sessionRefreshToken;
  const onAuthFailure = options.onAuthFailure ?? defaultOnAuthFailure;
  // Default to the global fetch (wrapped in an arrow so it isn't called detached from `globalThis`).
  const baseFetch: FetchImpl =
    (options.fetch as FetchImpl | undefined) ?? ((request) => fetch(request));
  const wrappedFetch = createRefreshRetryFetch(
    baseFetch,
    refreshAccessToken,
    onAuthFailure,
  );
  const client = createApiClient({ baseUrl, fetch: wrappedFetch });
  client.use(authMiddleware(getAccessToken));
  return client;
}

let cached: ApiClient | null = null;

/**
 * Get the process-wide authed API client, creating it on first use.
 *
 * Lazy (like the Supabase client) so public, env-less pages render without `VITE_*` vars; the
 * client is only built — and `readEnv()` only enforced — when the API is first called.
 */
export function getApiClient(): ApiClient {
  if (cached === null) {
    cached = createAuthedApiClient();
  }
  return cached;
}

/** Reset the cached client (tests; or after a config change). */
export function resetApiClient(): void {
  cached = null;
}
