/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Lengua FastAPI backend, e.g. http://localhost:8000 */
  readonly VITE_API_BASE_URL: string;
  /** Supabase project URL (auth only). */
  readonly VITE_SUPABASE_URL: string;
  /** Supabase anon/public key (safe to ship to the browser; auth only). */
  readonly VITE_SUPABASE_ANON_KEY: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
