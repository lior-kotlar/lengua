/**
 * Build-time environment for the web app.
 *
 * Vite statically inlines `import.meta.env.VITE_*` at build, so these are baked into the bundle.
 * We validate them at config-load / first-use and FAIL FAST with a clear, actionable error if a
 * required one is missing — rather than letting `undefined` propagate into the Supabase client or
 * API base URL and surface as a confusing runtime crash later.
 *
 * NOTE: a literal `vite build` cannot fail on a missing *runtime* value (it just inlines
 * `undefined`), and the CI build/E2E jobs intentionally build the bundle WITHOUT these vars (the
 * env-less home smoke must still render). So the fail-fast is enforced here, at the point of use,
 * and is covered by a unit test (`env.test.ts`). Screens that need Supabase reach it through
 * `getSupabaseClient()` (see `supabase.ts`), which calls `readEnv()` — so a misconfigured deploy
 * fails loudly the moment auth is touched, with the offending variable named.
 */

/** The validated, typed app environment. */
export interface AppEnv {
  /** Base URL of the Lengua FastAPI backend. */
  apiBaseUrl: string;
  /** Supabase project URL (auth only). */
  supabaseUrl: string;
  /** Supabase anon/public key (auth only). */
  supabaseAnonKey: string;
}

/** Required `VITE_*` variables, mapped to their `AppEnv` field. */
const REQUIRED_VARS = {
  VITE_API_BASE_URL: 'apiBaseUrl',
  VITE_SUPABASE_URL: 'supabaseUrl',
  VITE_SUPABASE_ANON_KEY: 'supabaseAnonKey',
} as const satisfies Record<string, keyof AppEnv>;

type RequiredVar = keyof typeof REQUIRED_VARS;

function isBlank(value: unknown): boolean {
  return value === undefined || value === null || String(value).trim() === '';
}

/**
 * Read + validate the app environment.
 *
 * @param source the env source (defaults to Vite's `import.meta.env`); injectable for tests.
 * @throws Error naming every missing/blank required variable.
 */
export function readEnv(
  source: Partial<Record<RequiredVar, string>> = import.meta.env,
): AppEnv {
  const missing = (Object.keys(REQUIRED_VARS) as RequiredVar[]).filter((name) =>
    isBlank(source[name]),
  );

  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variable(s): ${missing.join(', ')}. ` +
        `Set them in apps/web/.env (copy apps/web/.env.example) before building or running the web app.`,
    );
  }

  return {
    apiBaseUrl: source.VITE_API_BASE_URL!,
    supabaseUrl: source.VITE_SUPABASE_URL!,
    supabaseAnonKey: source.VITE_SUPABASE_ANON_KEY!,
  };
}
