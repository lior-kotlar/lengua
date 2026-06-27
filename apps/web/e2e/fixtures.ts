import { test as base } from '@playwright/test';

/**
 * Shared E2E `test` with the first-run analytics-consent banner pre-dismissed (group 4.10.3).
 *
 * The banner is an app-global, `fixed` bottom overlay shown until the user decides — handy in real
 * use, but in E2E it would sit over bottom-anchored controls and could intercept clicks. Seeding the
 * decision in an init script (before the app boots) keeps the banner out of the app specs without
 * each spec having to dismiss it. The dedicated `consent.spec.ts` imports the RAW `@playwright/test`
 * instead, so it can assert the genuine first-run banner behaviour.
 */
export const test = base.extend({
  // NOTE: the fixture's second arg is named `runTest` (not Playwright's conventional `use`) so the
  // eslint react-hooks/rules-of-hooks rule doesn't mistake `use(...)` for the React `use` hook.
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

export { expect } from '@playwright/test';
export type { Page } from '@playwright/test';
