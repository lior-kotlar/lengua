import fs from 'node:fs';

import { expect, test, type Page } from './fixtures';

/**
 * Account screen E2E (groups 4.8.2 + 4.8.3) — runs against the seeded demo account on the ephemeral
 * stack (Supabase + the API container).
 *
 *  - Export hits the REAL `GET /account/export` (a DB read, no LLM) and asserts a JSON download is
 *    offered.
 *  - Delete drives the confirm-typed dialog up to (and including) the confirmed click, but the
 *    `DELETE /account` call is STUBBED at the browser boundary so the shared demo account is NEVER
 *    actually deleted — we only assert the post-delete sign-out + redirect to /login. (Each test gets
 *    a fresh browser context, so the sign-out here doesn't leak to other specs.)
 *
 * Zero real LLM calls happen here (CI asserts the FakeLLM counter separately). Gated on E2E_STACK=1.
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const CONFIRM_PHRASE = 'delete my account';
const STACK = process.env.E2E_STACK === '1';

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

async function gotoAccount(page: Page) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Account' })
    .click();
  await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible();
}

test.describe('account screen (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('exports the account data as a downloadable JSON file', async ({
    page,
  }) => {
    await login(page);
    await gotoAccount(page);

    // The signed-in email shows in the profile card.
    await expect(page.getByTestId('account-email')).toHaveText(DEMO_EMAIL);

    // 4.8.2 — clicking export offers a JSON file download (real GET /account/export).
    const [response, download] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/account/export') &&
          r.request().method() === 'GET' &&
          r.ok(),
      ),
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export my data' }).click(),
    ]);
    expect(download.suggestedFilename()).toBe('lengua-export.json');

    // 8.2.3 launch-blocker: the downloaded file IS the GET /account/export response bundle.
    const apiBundle = await response.json();
    const savedPath = await download.path();
    const savedBundle = JSON.parse(fs.readFileSync(savedPath, 'utf-8'));
    expect(savedBundle).toEqual(apiBundle);
    // Sanity: it is the demo user's real bundle (all top-level keys, a non-empty deck). Sort both
    // sides so the assertion is order-independent ("proficiency" sorts before "profile").
    expect(Object.keys(savedBundle).sort()).toEqual(
      [
        'cards',
        'languages',
        'profile',
        'proficiency',
        'reviews',
        'settings',
      ].sort(),
    );
    expect(savedBundle.languages.length).toBeGreaterThan(0);
  });

  test('links to the published Privacy policy and Support pages (8.1.2)', async ({
    page,
  }) => {
    await login(page);
    await gotoAccount(page);

    // Scope to the main content region so we assert the Account-screen links, not the footer's.
    const main = page.getByRole('main');
    await expect(
      main.getByRole('link', { name: 'Privacy Policy' }),
    ).toHaveAttribute('href', '/privacy');
    await expect(main.getByRole('link', { name: 'Support' })).toHaveAttribute(
      'href',
      '/support',
    );
  });

  test('the delete dialog is confirm-typed and, once confirmed, signs out to /login', async ({
    page,
  }) => {
    await login(page);
    await gotoAccount(page);

    // Stub the hard-delete at the browser boundary so the real demo account is never deleted.
    let deleteCalls = 0;
    await page.route('**/account', async (route) => {
      if (route.request().method() !== 'DELETE') {
        await route.continue();
        return;
      }
      deleteCalls += 1;
      await route.fulfill({ status: 204, body: '' });
    });

    // Open the dialog from the danger zone (the trigger never deletes).
    await page.getByRole('button', { name: 'Delete account' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    const confirm = dialog.getByRole('button', { name: 'Delete account' });
    const phrase = dialog.getByLabel(/to confirm/i);

    // 4.8.3 — the confirm button stays disabled until the EXACT phrase is typed.
    await expect(confirm).toBeDisabled();
    await phrase.fill('delete');
    await expect(confirm).toBeDisabled();
    await phrase.fill(CONFIRM_PHRASE);
    await expect(confirm).toBeEnabled();

    // Confirming calls DELETE once, then signs out + redirects to /login.
    await confirm.click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: /log in/i })).toBeVisible();
    expect(deleteCalls).toBe(1);

    // Session is cleared: a protected route stays gated.
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('deletion is reachable via in-app navigation only and clears the session (8.2.4)', async ({
    page,
  }) => {
    await login(page);

    // Apple's in-app-deletion requirement: reach the delete control using ONLY in-app navigation —
    // the sidebar link, never an external URL or a direct goto. `gotoAccount` clicks the Primary nav.
    await gotoAccount(page);
    await expect(page).toHaveURL(/\/account$/);

    // Stub DELETE so the shared demo account survives; assert the session-clearing behaviour.
    await page.route('**/account', async (route) => {
      if (route.request().method() !== 'DELETE') {
        await route.continue();
        return;
      }
      await route.fulfill({ status: 204, body: '' });
    });

    await page.getByRole('button', { name: 'Delete account' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel(/to confirm/i).fill(CONFIRM_PHRASE);
    await dialog.getByRole('button', { name: 'Delete account' }).click();

    // The session is cleared: redirected to /login and a protected route stays gated afterwards.
    await expect(page).toHaveURL(/\/login$/);
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
  });
});
