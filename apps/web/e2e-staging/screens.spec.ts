import { expect, login, test, type Page } from './fixtures';

/**
 * Live-staging structural pass over the main authenticated screens (staging re-validation).
 *
 * Every assertion checks that a screen's STRUCTURE renders — headings, nav, a deck/form, or a
 * graceful empty state — never exact copy or seeded data, so the pass stays green whether or not
 * staging has been seeded. Uses role/testid selectors throughout and tolerates empty/loading
 * states. Runs ONLY via `playwright.staging.config.ts`; never in CI.
 */

/** Click a primary-nav link by its visible name and wait for the matching screen heading. */
async function navigateTo(page: Page, name: string): Promise<void> {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name })
    .click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
}

test('review shows a deck or a graceful empty state', async ({ page }) => {
  await login(page);
  await navigateTo(page, 'Review');
  // Either the due-counts header (a real deck) or an empty / all-caught-up card — both are valid
  // structural outcomes depending on whether staging has seeded due cards.
  const counts = page.getByTestId('review-counts');
  const emptyState = page.getByTestId('empty-state');
  await expect(counts.or(emptyState).first()).toBeVisible();
});

test('generate renders its word-entry form', async ({ page }) => {
  await login(page);
  await navigateTo(page, 'Generate');
  await expect(page.getByLabel('Words', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate' })).toBeVisible();
});

test('languages lists at least one language', async ({ page }) => {
  await login(page);
  await navigateTo(page, 'Languages');
  // The seeded demo has >= 1 language, each rendered as a row with a "Remove <name>" control.
  // Tolerate an unseeded account by also accepting the graceful empty message.
  const firstLanguageRow = page
    .getByRole('button', { name: /^Remove / })
    .first();
  const emptyLanguages = page.getByText(/haven't added any languages/i);
  await expect(firstLanguageRow.or(emptyLanguages).first()).toBeVisible();
});

test('settings renders its preferences form', async ({ page }) => {
  await login(page);
  await navigateTo(page, 'Settings');
  await expect(page.getByLabel('Daily new cards')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Save settings' }),
  ).toBeVisible();
});
