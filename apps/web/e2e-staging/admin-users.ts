/**
 * Admin user CRUD against the LIVE-staging Supabase Auth (GoTrue) — a helper module, NOT a test.
 *
 * The validation specs that need a *fresh* throwaway account (e.g. the signup / second-user flows)
 * import these helpers to admin-create a pre-confirmed user, then hard-delete it in cleanup so no
 * test users ever leak into `auth.users`. It mirrors the Python reference
 * (`apps/api/tests/supabase_auth.py`): same Auth Admin endpoints, same `service_role` headers.
 *
 * This file is deliberately NOT a `*.spec.ts` / `*.test.ts`, so Playwright never runs it as a test;
 * it is plain TypeScript imported by the staging specs (which run ONLY via
 * `playwright.staging.config.ts`, never in CI). It hits the deployed staging project directly using
 * the staging service-role secret, so every function reads its config from the environment and a
 * misconfig surfaces immediately as a thrown error.
 *
 * Env it reads (all three must be set for `adminConfigured()` to be true):
 *   - SUPABASE_STAGING_URL              — the staging project URL (e.g. https://<ref>.supabase.co)
 *   - SUPABASE_STAGING_ANON_KEY         — the staging anon (publishable) key
 *   - SUPABASE_STAGING_SERVICE_ROLE_KEY — the staging service-role secret (admin operations)
 */

/** An admin-created, pre-confirmed staging auth user (with the password it can log in with). */
export interface CreatedUser {
  id: string;
  email: string;
  password: string;
}

// Fixed default password for admin-created validation users. The admin create path bypasses the
// public signup password policy, so this only needs to let the user sign in via the real form.
const DEFAULT_PASSWORD = 'lengua-val-password-123';

/**
 * True iff the staging admin config is present (URL + anon + service-role). Specs `test.skip` when
 * this is false so the suite stays green on a machine without the staging secrets wired in.
 */
export function adminConfigured(): boolean {
  return Boolean(
    process.env.SUPABASE_STAGING_SERVICE_ROLE_KEY &&
    process.env.SUPABASE_STAGING_URL &&
    process.env.SUPABASE_STAGING_ANON_KEY,
  );
}

/**
 * Admin-create a PRE-CONFIRMED user via the Supabase Auth Admin API (`email_confirm: true`, so it
 * can sign in immediately). The email is unique by default. Throws on any non-2xx so a misconfigured
 * URL/secret surfaces loudly rather than silently producing a broken user.
 */
export async function createConfirmedUser(
  opts: { email?: string; password?: string } = {},
): Promise<CreatedUser> {
  const email = opts.email ?? `lengua-val-${crypto.randomUUID()}@lengua.test`;
  const password = opts.password ?? DEFAULT_PASSWORD;
  const res = await fetch(`${stagingUrl()}/auth/v1/admin/users`, {
    method: 'POST',
    headers: adminHeaders(),
    body: JSON.stringify({ email, password, email_confirm: true }),
  });
  if (!res.ok) {
    throw new Error(
      `Supabase admin create user failed (HTTP ${res.status}): ${await safeBody(res)}`,
    );
  }
  const body = (await res.json()) as { id?: string };
  if (!body.id) {
    throw new Error('Supabase admin create user returned no id');
  }
  return { id: body.id, email, password };
}

/**
 * Admin hard-delete a user by id. Best-effort cleanup for `afterAll`/`finally`: a 404 (already gone)
 * is treated as success and never throws; any other unexpected non-2xx throws so a real misconfig is
 * not swallowed.
 */
export async function deleteUser(userId: string): Promise<void> {
  const res = await fetch(`${stagingUrl()}/auth/v1/admin/users/${userId}`, {
    method: 'DELETE',
    headers: adminHeaders(),
  });
  // 200/204 = deleted; 404 = already gone. Anything else is a genuine error worth surfacing.
  if (res.ok || res.status === 404) {
    return;
  }
  throw new Error(
    `Supabase admin delete user failed (HTTP ${res.status}): ${await safeBody(res)}`,
  );
}

/**
 * Admin-lookup a user id by email — used to clean up a user created via the *public* signup form
 * (where the spec only knows the email, not the id). Returns null if no user has that email.
 *
 * GoTrue's admin list endpoint has no server-side email filter, so we page through and match
 * client-side (case-insensitive), stopping on the first empty page. A hard page cap guards against
 * an unexpectedly huge/looping response.
 */
export async function findUserByEmail(
  email: string,
): Promise<{ id: string } | null> {
  const target = email.trim().toLowerCase();
  const perPage = 100;
  const maxPages = 100; // safety bound (≤ ~10k users) so a misconfig can never loop forever
  for (let page = 1; page <= maxPages; page += 1) {
    const res = await fetch(
      `${stagingUrl()}/auth/v1/admin/users?page=${page}&per_page=${perPage}`,
      { headers: adminHeaders() },
    );
    if (!res.ok) {
      throw new Error(
        `Supabase admin list users failed (HTTP ${res.status}): ${await safeBody(res)}`,
      );
    }
    const body = (await res.json()) as {
      users?: Array<{ id: string; email?: string | null }>;
    };
    const users = body.users ?? [];
    if (users.length === 0) {
      break; // reached past the last page
    }
    const match = users.find((u) => (u.email ?? '').toLowerCase() === target);
    if (match) {
      return { id: match.id };
    }
  }
  return null;
}

/** Read a required staging env var, throwing a clear error if it is missing. */
function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is required for staging admin user operations but is not set`,
    );
  }
  return value;
}

/** The staging Supabase project URL, with any trailing slash trimmed. */
function stagingUrl(): string {
  return requireEnv('SUPABASE_STAGING_URL').replace(/\/+$/, '');
}

/** Service-role auth headers for the Supabase Auth Admin API (mirrors the Python `_auth_headers`). */
function adminHeaders(): Record<string, string> {
  const key = requireEnv('SUPABASE_STAGING_SERVICE_ROLE_KEY');
  return {
    apikey: key,
    Authorization: `Bearer ${key}`,
    'Content-Type': 'application/json',
  };
}

/** Best-effort read of a (truncated) response body for error messages; never throws. */
async function safeBody(res: Response): Promise<string> {
  try {
    return (await res.text()).slice(0, 500);
  } catch {
    return '<no body>';
  }
}
