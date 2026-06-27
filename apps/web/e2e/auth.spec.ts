import { expect, test } from '@playwright/test';

/**
 * Auth + session E2E (group 4.3).
 *
 * Two tiers:
 *  - The route-gating smoke runs anywhere: even the env-less local preview renders (the AuthProvider
 *    degrades to signed-out when Supabase env is absent), so a logged-out visit to `/` redirects to
 *    `/login`.
 *  - The sign-up / log-in / sign-out flows need the real ephemeral stack (Supabase + the API
 *    container) wired into the build, so they are gated on `E2E_STACK=1` (set by the CI e2e job).
 *    Locally, run them with the stack up + the bundle built against it.
 *
 * The seeded demo account comes from apps/api/scripts/seed_e2e.py (email pre-confirmed via the Auth
 * Admin API). Zero real LLM calls happen here — none of these flows touch the LLM seam; the CI job
 * separately asserts the FakeLLM call counter.
 *
 * The 401 → refresh-once → retry path (task 4.3.7) is covered exhaustively in vitest
 * (src/lib/api-client.test.ts): forcing a mid-session 401 against a healthy local API is not
 * reliably reproducible, so it is verified at the unit layer rather than here.
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

test('a logged-out visit to / redirects to the login screen', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: /log in/i })).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
  // OAuth buttons are present on the login screen (task 4.3.5).
  await expect(
    page.getByRole('button', { name: 'Continue with Google' }),
  ).toBeVisible();
});

test.describe('auth flows (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('signing up a fresh email shows the verify-notice screen', async ({
    page,
  }) => {
    const email = `e2e+${Date.now()}@lengua.test`;
    await page.goto('/signup');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password', { exact: true }).fill('Abcdef12');
    await page.getByLabel('Confirm password').fill('Abcdef12');
    await page.getByRole('button', { name: /create account/i }).click();

    await expect(
      page.getByRole('heading', { name: /check your email/i }),
    ).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
  });

  test('logging in the demo account reaches home, then sign-out re-gates', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(DEMO_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
    await page.getByRole('button', { name: 'Log in' }).click();

    // Lands on the authenticated app shell.
    await expect(
      page.getByRole('heading', { name: 'Dashboard' }),
    ).toBeVisible();
    await expect(
      page.getByRole('navigation', { name: 'Primary' }),
    ).toBeVisible();
    await expect(page).not.toHaveURL(/\/login$/);

    // Sign out → back to /login, and protected routes stay gated.
    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });
});
