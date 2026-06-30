import { expect, login, test } from './fixtures';

/**
 * Live-staging auth pass (staging re-validation). Structure-only assertions against the deployed
 * site — no exact-copy or seeded-data matching. Runs ONLY via `playwright.staging.config.ts`, never
 * in CI. See `fixtures.ts` for the shared `login` helper + consent pre-dismissal.
 */

test('a logged-out visit to / redirects to the login screen', async ({
  page,
}) => {
  await page.goto('/');
  // RequireAuth bounces an unauthenticated visit to /login (tolerate an optional return-to query).
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole('heading', { name: /log in/i })).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
});

test('the demo user can log in and reach the app shell', async ({ page }) => {
  await login(page);
  // The authenticated shell renders its primary navigation, and we are no longer on /login.
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page).not.toHaveURL(/\/login/);
});
