import AxeBuilder from '@axe-core/playwright';

import { expect, test, type Page } from './fixtures';

/**
 * Advisory accessibility sweep (axe-core) over the AUTHENTICATED surfaces — broadens the CI a11y
 * pass beyond the static `/login` page, which `.github/workflows/ci.yml`'s `a11y-perf` job already
 * scans with `@axe-core/cli`. This spec runs under the FakeLLM e2e harness the `e2e` job stands up
 * (seeded demo account + API container with `LLM_PROVIDER=fake` + the served web bundle), logs in as
 * the demo user, and runs axe on Dashboard / Generate / Review / Discover / Settings.
 *
 * ADVISORY, never a merge gate: it NEVER asserts zero violations — it counts + logs them
 * (`console.warn`) and attaches the full axe report per screen, then always passes. In CI the `e2e`
 * job grep-excludes this `@a11y`-tagged spec from the REQUIRED Playwright run and runs it as a
 * separate `|| echo` step, so a11y findings surface without blocking merges. Gated on `E2E_STACK=1`
 * like the other authenticated flows.
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

/** Click a primary-nav link by its visible name and wait for the matching screen heading. */
async function navigateTo(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name })
    .click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
}

/**
 * Run axe on the current page and REPORT — never fail. Attaches the full per-screen violation list
 * to the Playwright report and logs a one-line summary; any axe/page error is swallowed (advisory).
 */
async function auditScreen(page: Page, screen: string) {
  try {
    const { violations } = await new AxeBuilder({ page }).analyze();
    await test.info().attach(`axe-${screen}.json`, {
      body: JSON.stringify(violations, null, 2),
      contentType: 'application/json',
    });
    if (violations.length === 0) {
      console.log(`[a11y] ${screen}: no violations`);
      return;
    }
    const summary = violations
      .map((v) => `${v.id} (${v.impact ?? 'n/a'}) x${v.nodes.length}`)
      .join(', ');
    console.warn(
      `[a11y] ${screen}: ${violations.length} violation type(s) — ${summary}`,
    );
  } catch (err) {
    console.warn(
      `[a11y] ${screen}: axe run errored (advisory, ignored): ${String(err)}`,
    );
  }
}

test.describe('accessibility (axe, advisory) @a11y', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('axe sweep of the authenticated surfaces (advisory, non-blocking)', async ({
    page,
  }) => {
    await login(page);
    await auditScreen(page, 'dashboard');

    // Best-effort per screen: a flaky navigation on one surface must not abort auditing the rest
    // (this whole spec is advisory — the CI step also wraps it in `|| echo`).
    for (const screen of ['Generate', 'Review', 'Discover', 'Settings']) {
      try {
        await navigateTo(page, screen);
        await auditScreen(page, screen.toLowerCase());
      } catch (err) {
        console.warn(
          `[a11y] ${screen}: navigation failed (advisory, skipped): ${String(err)}`,
        );
      }
    }
  });
});
