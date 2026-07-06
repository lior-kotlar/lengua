import { adminConfigured, deleteUser, findUserByEmail } from './admin-users';
import { expect, test } from './fixtures';

/**
 * Live-staging Layer A pass over the PUBLIC sign-up form (staging re-validation). It drives the real
 * `/signup` form on the deployed site with a unique disposable email + a policy-valid password,
 * submits "Create account", and asserts the sign-up SUCCEEDS — accepting EITHER post-sign-up state so
 * the spec is robust to the project's email-confirmation setting:
 *   - confirmation ON  → the "Check your email" verification notice renders; or
 *   - confirmation OFF → the user is auto-confirmed and lands in the authenticated app shell.
 * (Staging currently runs with confirmation OFF as an interim unblock while custom SMTP is
 * unconfigured — see the root CHANGELOG.md (live-staging validation) and issue #103.) In the
 * confirmation-OFF case it then proves the full register -> sign out -> log back in loop with the same
 * credentials. It never clicks an email verification link.
 *
 * Sign-up creates a row in `auth.users`, so `afterAll` admin-deletes it (via the service-role helpers
 * in `./admin-users`) to leave staging exactly as found. Because that cleanup is only possible with
 * the staging service-role secret, the test SKIPS itself when the admin config is absent — otherwise
 * it would leak a user it cannot remove. Runs ONLY via `playwright.staging.config.ts`, never in CI.
 * See `fixtures.ts` for the consent pre-dismissal.
 */

// Unique disposable email so repeat runs never collide; module-scoped so `afterAll` can clean it up.
const signupEmail = `lengua-signup-${crypto.randomUUID()}@lengua.test`;
// A policy-valid password (>= 8 chars, lower + upper + digit), mirroring `src/lib/auth-validation.ts`.
// Fixed FAKE test-fixture password (not a real credential); the inline directive stops the secrets
// scanner's generic high-entropy heuristic from flagging this known test value.
const signupPassword = 'Lengua-Signup-123'; // gitleaks:allow

test('a new user can register and sign in via the public sign-up form', async ({
  page,
}) => {
  // Skip when the staging service-role secret is absent: without it we cannot admin-delete the user
  // this form creates, so running it would leak a row into `auth.users`.
  test.skip(
    !adminConfigured(),
    'requires the staging service-role secret to clean up the sign-up user',
  );

  await page.goto('/signup');
  // The unauthenticated sign-up screen renders its form.
  await expect(page.getByRole('heading', { name: 'Sign up' })).toBeVisible();

  await page.getByLabel('Email').fill(signupEmail);
  // `exact` so this targets "Password" and not the separate "Confirm password" field.
  await page.getByLabel('Password', { exact: true }).fill(signupPassword);
  await page.getByLabel('Confirm password').fill(signupPassword);

  await page.getByRole('button', { name: 'Create account' }).click();

  // Success — accept EITHER post-sign-up state (robust to the email-confirmation toggle):
  //  - confirmation ON  → the "Check your email" verification notice renders; or
  //  - confirmation OFF → the user is auto-confirmed and lands in the authenticated app shell.
  // Reaching either proves sign-up succeeded (the old HTTP 500 blocker left the form on screen).
  const checkEmail = page.getByRole('heading', { name: 'Check your email' });
  const appShell = page.getByRole('navigation', { name: 'Primary' });
  await expect(checkEmail.or(appShell).first()).toBeVisible();

  // With email confirmation OFF (the current staging setting) sign-up auto-confirms the user and
  // lands them in the app, so we can prove the full register -> sign out -> log back in loop with the
  // same credentials. (When confirmation is ON, "Check your email" shows and we cannot log in without
  // the email link, so registration alone is the assertion.)
  // Auto-confirm returns a session that redirects into the app; wait that redirect out (rather than
  // sampling visibility mid-transition) to decide whether the login loop applies.
  const landedInApp = await appShell
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => true)
    .catch(() => false);
  if (landedInApp) {
    await page
      .getByRole('banner')
      .getByRole('button', { name: 'Sign out' })
      .click();
    await expect(page).toHaveURL(/\/login/);

    await page.getByLabel('Email').fill(signupEmail);
    await page.getByLabel('Password', { exact: true }).fill(signupPassword);
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(
      page.getByRole('navigation', { name: 'Primary' }),
    ).toBeVisible();
  }
});

test.afterAll(async () => {
  // Best-effort cleanup: hard-delete the user the public sign-up created so staging is left exactly
  // as found. Guarded by `adminConfigured()` (the test is skipped without it, so no user exists to
  // remove) and wrapped so a cleanup hiccup never fails the pass.
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
