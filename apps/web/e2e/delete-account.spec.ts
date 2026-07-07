import { expect, test } from './fixtures';

/**
 * Public compliance surfaces (Phase 8, tasks 8.1.2 + 8.3.1) — the store-required pages that must be
 * reachable WITHOUT signing in: the Privacy policy, the Support page, and the external
 * account-deletion request form (Google Play requires a deletion path usable without the app).
 *
 * The form submit hits the REAL `POST /account/deletion-request` on the ephemeral stack; it is
 * non-destructive — an unknown email yields the same generic acknowledgement and deletes nothing
 * (actual deletion needs the emailed confirmation token). Gated on E2E_STACK=1 for that reason.
 */

const STACK = process.env.E2E_STACK === '1';

test('privacy and support pages are reachable without signing in', async ({
  page,
}) => {
  await page.goto('/privacy');
  await expect(
    page.getByRole('heading', { level: 1, name: /privacy policy/i }),
  ).toBeVisible();

  await page.goto('/support');
  await expect(
    page.getByRole('heading', { level: 1, name: /^support$/i }),
  ).toBeVisible();
});

test('the public delete-account form is reachable without login and acknowledges a request', async ({
  page,
}) => {
  test.skip(
    !STACK,
    'the form submit hits the ephemeral API stack (E2E_STACK=1)',
  );

  await page.goto('/delete-account');
  await expect(
    page.getByRole('heading', { level: 1, name: /delete your account/i }),
  ).toBeVisible();

  // A throwaway (unregistered) email: the endpoint returns the same generic ack and deletes nothing.
  await page.getByLabel('Account email').fill('nobody-e2e@example.com');
  await page.getByRole('button', { name: /request account deletion/i }).click();

  await expect(page.getByText(/if an account exists/i)).toBeVisible();
});
