/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Lengua FastAPI backend, e.g. http://localhost:8000 */
  readonly VITE_API_BASE_URL: string;
  /** Supabase project URL (auth only). */
  readonly VITE_SUPABASE_URL: string;
  /** Supabase anon/public key (safe to ship to the browser; auth only). */
  readonly VITE_SUPABASE_ANON_KEY: string;
  /**
   * Optional comma-separated OAuth providers to enable on the auth screens (e.g. "google,apple").
   * Defaults to both when unset; set to a narrower list (or empty) per environment until live
   * provider credentials are wired. See `oauth-buttons.tsx`.
   */
  readonly VITE_OAUTH_PROVIDERS?: string;
  /**
   * Optional PostHog project key for EU-hosted product analytics (group 5.9). Analytics loads ONLY
   * after the user opts in (consent banner / Settings toggle) AND this key is set; posthog-js is then
   * lazily code-split in. Unset → analytics never loads or sends, even with consent. See
   * `lib/posthog.ts` + `lib/analytics.ts`.
   */
  readonly VITE_POSTHOG_KEY?: string;
  /**
   * Optional browser Sentry DSN (task 5.4.2). Sentry initialises ONLY when set; unset → nothing
   * loads, zero egress. Separate from the backend `SENTRY_DSN_API`; renames the old non-prefixed
   * `SENTRY_DSN_WEB` so it can reach the bundle. See `lib/error-tracking.ts`.
   */
  readonly VITE_SENTRY_DSN_WEB?: string;
  /**
   * Optional dev/test-only flag (`"1"`/`"true"`). Enables the hidden Sentry debug-error button and
   * records captures on `window` for the E2E assertion. A production build NEVER sets it, so the
   * button can never render/trigger in a deployed app. See `components/debug-error-button.tsx`.
   */
  readonly VITE_ENABLE_DEBUG_TOOLS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
