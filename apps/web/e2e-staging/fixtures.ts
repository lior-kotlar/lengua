import { test as base, expect, type Page } from '@playwright/test';

/**
 * Shared fixtures + helpers for the LIVE-staging browser pass (NOT part of CI).
 *
 * Mirrors `e2e/fixtures.ts`: the first-run analytics-consent banner is a `fixed` bottom overlay that
 * can intercept clicks, so we pre-seed the "denied" decision in an init script before the app boots.
 * Also centralises the demo credentials (env-overridable for the orchestrator) and a `login` helper
 * so every staging spec signs in the same way.
 *
 * These specs hit the deployed staging site and are run only on demand via `test:e2e-staging`
 * (see `playwright.staging.config.ts`). They are never wired into `ci.yml`, the default
 * `playwright test`, vitest, or coverage.
 */
const DEMO_EMAIL = process.env.DEMO_EMAIL ?? 'demo@lengua.test';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? 'demo-password-123';

export const test = base.extend({
  // The fixture's second arg is named `runTest` (not Playwright's conventional `use`) so the eslint
  // react-hooks rule doesn't mistake `use(...)` for the React `use` hook — same as e2e/fixtures.ts.
  page: async ({ page }, runTest) => {
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('lengua.analytics-consent', 'denied');
      } catch {
        // localStorage may be unavailable in some sandboxes; the banner is non-fatal.
      }
    });
    await runTest(page);
  },
});

export { expect };
export type { Page };

/**
 * Sign in the seeded demo user through the real login form and wait for the authenticated shell.
 * Structure-only: it asserts the Primary navigation (the authenticated shell) renders, never any
 * seeded content. We wait for the shell — not the "Dashboard" heading — because a login that follows
 * a sign-out from another screen is correctly returned to that originally-requested route
 * (`RequireAuth` stores `from`; `RedirectIfAuthed` restores it), so it does NOT always land on the
 * Dashboard. The Primary nav renders on every signed-in screen, so it is the reliable shell marker.
 */
export async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
}
