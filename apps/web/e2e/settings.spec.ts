import { expect, test, type Page } from '@playwright/test';

/**
 * Settings screen E2E (group 4.8.1) — runs against the seeded demo account on the ephemeral stack
 * (Supabase + the API container). Settings are plain DB-backed key/values, so this touches no LLM
 * seam (zero real LLM calls; CI asserts the FakeLLM counter separately). Gated on E2E_STACK=1 like
 * the other authed flows.
 *
 * Note: the Save button writes all three editable settings; the Discover default count is written as
 * its current value (5, the server default), so the Discover spec's "defaults to 5" assertion is
 * unaffected. The review-limit keys have no effect on other specs (the review batch uses the server
 * config defaults today), so changing them here is safe.
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

async function gotoSettings(page: Page) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Settings' })
    .click();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
}

test.describe('settings screen (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('changing the daily new-card limit saves and persists across a reload', async ({
    page,
  }) => {
    await login(page);
    await gotoSettings(page);

    const newCards = page.getByLabel('Daily new cards');
    await expect(newCards).toBeVisible();

    await newCards.fill('7');
    // Save and wait for the PUT to land before reloading, so persistence is genuinely round-tripped.
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/settings') &&
          r.request().method() === 'PUT' &&
          r.ok(),
      ),
      page.getByRole('button', { name: 'Save settings' }).click(),
    ]);
    await expect(page.getByText('Settings saved')).toBeVisible();

    // Reload: the value is fetched fresh from the backend and still 7.
    await page.reload();
    await expect(page.getByLabel('Daily new cards')).toHaveValue('7');
  });

  test('blocks saving a value outside the allowed bounds', async ({ page }) => {
    await login(page);
    await gotoSettings(page);

    await page.getByLabel('Daily new cards').fill('0');
    await expect(page.getByText('Must be between 1 and 100.')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Save settings' }),
    ).toBeDisabled();
  });
});
