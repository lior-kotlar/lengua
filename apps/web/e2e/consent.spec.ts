import { expect, test } from '@playwright/test';

/**
 * First-run analytics-consent banner E2E (group 4.10.3).
 *
 * Runs on the plain local preview — no ephemeral stack / no auth needed — because the banner is
 * app-global and shows even on the logged-out `/login` screen. It asserts:
 *  - the banner shows on first load,
 *  - NO analytics request fires before a decision (the privacy guarantee; the preview build has no
 *    `VITE_POSTHOG_KEY`, so nothing loads even on opt-in — a clean seam), and
 *  - the choice persists across a reload, so the banner never re-prompts once decided.
 *
 * NOTE: this spec uses the RAW `@playwright/test` (not `./fixtures`) so the banner is NOT
 * pre-dismissed — the app specs seed the decision via the shared fixture to keep the overlay out of
 * their way.
 */

const ANALYTICS_HOST = /posthog|i\.posthog\.com|analytics/i;
const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

test('shows the consent banner on first load and never loads analytics before a decision', async ({
  page,
}) => {
  const analyticsRequests: string[] = [];
  page.on('request', (request) => {
    if (ANALYTICS_HOST.test(request.url())) {
      analyticsRequests.push(request.url());
    }
  });

  await page.goto('/');
  const banner = page.getByTestId('analytics-consent');
  await expect(banner).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Analytics consent' }),
  ).toBeVisible();
  // Nothing analytics-related loaded before the user decided.
  expect(analyticsRequests).toEqual([]);

  // Decline → banner dismissed immediately.
  await page.getByRole('button', { name: 'Decline' }).click();
  await expect(banner).toBeHidden();

  // …and the decision persists across a reload (no re-prompt).
  await page.reload();
  await expect(page.getByTestId('analytics-consent')).toHaveCount(0);
  // Still no analytics loaded (declined).
  expect(analyticsRequests).toEqual([]);
});

test('accepting the consent dismisses it permanently and loads no analytics (no key configured)', async ({
  page,
}) => {
  const analyticsRequests: string[] = [];
  page.on('request', (request) => {
    if (ANALYTICS_HOST.test(request.url())) {
      analyticsRequests.push(request.url());
    }
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Accept' }).click();
  await expect(page.getByTestId('analytics-consent')).toBeHidden();

  await page.reload();
  await expect(page.getByTestId('analytics-consent')).toHaveCount(0);
  // The preview build ships no analytics key, so opting in still loads nothing (clean seam).
  expect(analyticsRequests).toEqual([]);
});

/**
 * Launch-blocker (task 8.2.1): declining consent must leave analytics fully uninitialised for the
 * WHOLE session, not just the login page. We decline, then drive a full authenticated journey across
 * every screen and assert not a single analytics request fired. (The network invariant is proven
 * here; that the gate blocks even WITH a key configured is proven at the unit level in
 * `src/lib/analytics.test.ts`, which the preview's key-less build cannot exercise.)
 */
test('declining consent loads no analytics across a full authenticated session (8.2.1)', async ({
  page,
}) => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  const analyticsRequests: string[] = [];
  page.on('request', (request) => {
    if (ANALYTICS_HOST.test(request.url())) {
      analyticsRequests.push(request.url());
    }
  });

  await page.goto('/login');
  // Decline up front (raw spec → the banner is shown, not pre-dismissed by the fixture).
  await page.getByRole('button', { name: 'Decline' }).click();
  await expect(page.getByTestId('analytics-consent')).toBeHidden();

  // Log in and visit every primary screen — a full session.
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  for (const name of [
    'Generate',
    'Review',
    'Discover',
    'Languages',
    'Settings',
    'Account',
  ]) {
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name })
      .click();
    await expect(page.getByRole('heading', { name })).toBeVisible();
  }

  // Across the entire declined session, zero analytics requests fired.
  expect(analyticsRequests).toEqual([]);
});
