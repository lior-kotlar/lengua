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
   * Optional PostHog project key for product analytics. Analytics loads ONLY after the user opts in
   * via the consent banner AND this key is set (group 4.10.3; wired fully in Phase 5/8). Unset →
   * analytics never loads, even with consent. See `lib/analytics.ts`.
   */
  readonly VITE_POSTHOG_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
