/**
 * Supabase client — AUTH ONLY.
 *
 * Supabase is used exclusively for authentication (sessions, tokens, OAuth). All application data
 * goes through the typed API client against the FastAPI backend, never the Supabase data APIs.
 *
 * The client is created lazily on first use (not at module import) so that public pages render
 * without env vars present (e.g. the env-less E2E home smoke), while any auth-touching screen fails
 * fast via `readEnv()` if the deploy is misconfigured.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import { readEnv } from '@/lib/env';

let cached: SupabaseClient | null = null;

/**
 * Get the process-wide Supabase client, creating it on first call.
 *
 * @throws Error (via `readEnv`) if a required `VITE_*` var is missing.
 */
export function getSupabaseClient(): SupabaseClient {
  if (cached === null) {
    const env = readEnv();
    cached = createClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return cached;
}
