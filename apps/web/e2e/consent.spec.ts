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
