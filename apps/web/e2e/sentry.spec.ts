import { expect, test } from '@playwright/test';

/**
 * Web Sentry debug-capture E2E (group 5.4.2).
 *
 * Runs on the plain local preview — no ephemeral stack / no auth — because the hidden Sentry
 * debug-error button is app-global (it shows even on the logged-out screen) when the build sets
 * `VITE_ENABLE_DEBUG_TOOLS=1` (the local Playwright build + the CI e2e build both do). Uses the RAW
 * `@playwright/test` (not `./fixtures`) so nothing pre-dismisses the consent banner.
 *
 * It asserts the verify for 5.4.2 with ZERO real egress: the preview build configures NO
 * `VITE_SENTRY_DSN_WEB`, so Sentry never initialises and never sends anything — yet clicking the
 * button still drives the app's capture chokepoint (recorded on `window` for this assertion) AND
 * genuinely throws. So the capture path is proven to fire while no Sentry network request is made.
 */

const SENTRY_HOST = /sentry|ingest/i;
const DEBUG_MESSAGE = 'Sentry web debug test error';

test('the hidden debug button fires the Sentry capture path with zero egress', async ({
  page,
}) => {
  const sentryRequests: string[] = [];
  page.on('request', (request) => {
    if (SENTRY_HOST.test(request.url())) {
      sentryRequests.push(request.url());
    }
  });
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });

  await page.goto('/');

  // The button is present only because this build sets VITE_ENABLE_DEBUG_TOOLS=1; it is sr-only
  // (truly hidden, off-screen), so dispatch the click event directly rather than a pointer click
  // (which requires the element to be in the viewport).
  const button = page.getByTestId('debug-throw-error');
  await expect(button).toBeAttached();
  await button.dispatchEvent('click');

  // The capture chokepoint recorded the error (proof the Sentry capture path fired). With no DSN in
  // this build, nothing is sent — the record on window is the zero-egress observable signal.
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { __SENTRY_TEST_CAPTURES__?: string[] })
            .__SENTRY_TEST_CAPTURES__ ?? [],
      ),
    )
    .toContain(DEBUG_MESSAGE);

  // The button genuinely throws (it "throws"), surfacing as an uncaught page error.
  await expect
    .poll(() => pageErrors.some((message) => message.includes(DEBUG_MESSAGE)))
    .toBe(true);

  // No real Sentry network request was made at any point (zero egress in CI).
  expect(sentryRequests).toEqual([]);
});
