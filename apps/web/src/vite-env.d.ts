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
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
