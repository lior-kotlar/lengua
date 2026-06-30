import { adminConfigured, deleteUser, findUserByEmail } from './admin-users';
import { expect, test } from './fixtures';

/**
 * Live-staging Layer A pass over the PUBLIC sign-up form (staging re-validation). It drives the real
 * `/signup` form on the deployed site with a unique disposable email + a policy-valid password,
 * submits "Create account", and asserts the "Check your email" verification notice renders. It does
 * NOT confirm the email (impossible to automate) and does NOT log in afterward.
 *
 * Public sign-up leaves an UNCONFIRMED row in `auth.users`, so `afterAll` admin-deletes it (via the
 * service-role helpers in `./admin-users`) to leave staging exactly as found. Because that cleanup
 * is only possible with the staging service-role secret, the test SKIPS itself when the admin config
 * is absent — otherwise it would leak a user it cannot remove. Runs ONLY via
 * `playwright.staging.config.ts`, never in CI. See `fixtures.ts` for the consent pre-dismissal.
 */

// Unique disposable email so repeat runs never collide; module-scoped so `afterAll` can clean it up.
const signupEmail = `lengua-signup-${crypto.randomUUID()}@lengua.test`;
// A policy-valid password (>= 8 chars, lower + upper + digit), mirroring `src/lib/auth-validation.ts`.
// Fixed FAKE test-fixture password (not a real credential); the inline directive stops the secrets
// scanner's generic high-entropy heuristic from flagging this known test value.
const signupPassword = 'Lengua-Signup-123'; // gitleaks:allow

test('a visitor can submit the sign-up form and see the verification notice', async ({
  page,
}) => {
  // Skip when the staging service-role secret is absent: without it we cannot admin-delete the
  // unconfirmed user this form creates, so running it would leak a row into `auth.users`.
  test.skip(
    !adminConfigured(),
    'requires the staging service-role secret to clean up the unconfirmed sign-up user',
  );

  await page.goto('/signup');
  // The unauthenticated sign-up screen renders its form.
  await expect(page.getByRole('heading', { name: 'Sign up' })).toBeVisible();

  await page.getByLabel('Email').fill(signupEmail);
  // `exact` so this targets "Password" and not the separate "Confirm password" field.
  await page.getByLabel('Password', { exact: true }).fill(signupPassword);
  await page.getByLabel('Confirm password').fill(signupPassword);

  await page.getByRole('button', { name: 'Create account' }).click();

  // Success state: the form is replaced by a "Check your email" confirmation that echoes the address
  // we signed up with. Email confirmation is required, so the user stays logged out — we go no further.
  await expect(
    page.getByRole('heading', { name: 'Check your email' }),
  ).toBeVisible();
  await expect(page.getByText(signupEmail)).toBeVisible();
});

test.afterAll(async () => {
  // Best-effort cleanup: hard-delete the unconfirmed user the public sign-up created so staging is
  // left exactly as found. Guarded by `adminConfigured()` (the test is skipped without it, so no user
  // exists to remove) and wrapped so a cleanup hiccup never fails the pass.
  if (!adminConfigured()) {
    return;
  }
  try {
    const user = await findUserByEmail(signupEmail);
    if (user) {
      await deleteUser(user.id);
    }
  } catch {
    // Swallow cleanup errors — a leaked unconfirmed test user is not worth failing the pass over.
  }
});
