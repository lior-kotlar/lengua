import { expect, test, type Page } from './fixtures';
import {
  adminConfigured,
  createConfirmedUser,
  deleteUser,
  type CreatedUser,
} from './admin-users';

/**
 * Layer C — the fresh-user / multi-language / account-lifecycle driver (staging re-validation).
 *
 * This is the "mock users learning 2+ languages, end to end, then gone" scenario. It admin-creates
 * TWO pre-confirmed throwaway users via the Supabase Auth Admin API (see `admin-users.ts`), then
 * drives EACH through the entire SYNTHESIS Blocker-4 journey in a real browser — including the
 * DESTRUCTIVE step 22 (delete account), which the demo `full-flow.spec.ts` deliberately omits:
 *
 *   log in via the form → add language A (non-RTL, level B1) → confirm its CEFR band → add language
 *   B (Hebrew, code "he", vowel marks → RTL) → SWITCH between A and B (the CEFR band flips per
 *   language) → assert B renders right-to-left and the vowel-marks switch toggles → (LLM-gated)
 *   generate + save + study A grading ONLY "Again" → (LLM-gated) Discover → Settings save → Account
 *   → sign out → log back in (languages + decks survive) → DELETE the account → land on /login.
 *
 * Guardrails baked in (VALIDATION-PLAN §5):
 *  - Fresh users (NOT the shared demo account): every account created here is admin-created with a
 *    unique email and is HARD-DELETED — once through the UI (the lifecycle's final step) and again,
 *    defensively, in `afterAll` (best-effort, 404-tolerant) — so zero `auth.users` rows ever leak.
 *    Deleting the auth user cascades away its languages + cards (migration 0006), so no per-language
 *    cleanup is needed.
 *  - Review grades ONLY "Again" (data-rating="1") and the walk is FORWARD-ONLY (never asserts a
 *    return to a prior card).
 *  - Every LLM-touching sub-step (generate / save / review tap-a-word / discover) is gated behind
 *    STAGING_INCLUDE_LLM and is 429/503-TOLERANT: a fired cost guard is correct behaviour, treated
 *    as an acceptable PASS that short-circuits the rest of that sub-step. Structure/read-only
 *    assertions (add/switch language, CEFR band, RTL, settings, account, auth, delete) always run.
 *  - Each fresh user generates AT MOST ONCE (lang A only), well under the day-0 new-account generate
 *    cap of 5; words are tiny + timestamp-unique so repeat runs never collide.
 *  - The two users run SERIALLY (`mode: 'serial'`), so this file never puts more than one fresh
 *    real-LLM user in flight at a time — comfortably under the ≤3–4 concurrent-user ceiling.
 *
 * When the staging service-role secret is absent (a Tier A run) the whole group is SKIPPED — the
 * admin API is the only way to mint a usable confirmed user, so there is nothing to drive without it.
 *
 * Runs ONLY via `playwright.staging.config.ts` (`pnpm test:e2e-staging`), never in CI. See
 * `fixtures.ts` for the consent pre-dismissal that the imported `test` carries.
 */

/** Only fire the (quota-bounded, real-Groq) LLM sub-steps when explicitly opted in. */
const INCLUDE_LLM = Boolean(process.env.STAGING_INCLUDE_LLM);

/** Generous budget for a real `/generate` or `/discover` (cold Cloud Run + real Groq are slow). */
const LLM_TIMEOUT = 60_000;

/** How many fresh throwaway users to provision + drive (kept low to bound real-LLM concurrency). */
const USER_COUNT = 2;

/** The exact phrase the delete-account dialog requires (mirrors `DELETE_CONFIRM_PHRASE`). */
const DELETE_CONFIRM_PHRASE = 'delete my account';

/** Every user we admin-create, so `afterAll` can hard-delete each one even if its test failed. */
const createdUsers: CreatedUser[] = [];

/** Click a primary-nav link by its visible name and wait for the matching screen heading. */
async function navigateTo(page: Page, name: string): Promise<void> {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name })
    .click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
}

/** The reveal button of whichever review card is up (production / recognition share the regex). */
function revealButton(page: Page) {
  return page.getByRole('button', { name: /^Show (answer|translation)$/ });
}

/** Switch the active language via the always-present header picker (the robust, unambiguous path). */
async function switchActiveLanguage(page: Page, name: string): Promise<void> {
  await page.getByLabel('Active language').selectOption({ label: name });
}

/**
 * Sign a fresh admin-created user in through the real login form and wait for the authenticated
 * shell. We assert the Primary navigation — not the "Dashboard" heading — because a login that
 * follows a sign-out from another screen is correctly returned to that originally-requested route
 * (`RequireAuth` stores `from`; `RedirectIfAuthed` restores it), so re-login does NOT always land on
 * the Dashboard. The Primary nav renders on every signed-in screen, so it is the reliable marker.
 */
async function loginAs(page: Page, user: CreatedUser): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password', { exact: true }).fill(user.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
}

/**
 * Fill + submit the "Add a language" form via the custom (experimental) path (issue #95).
 * These tests use timestamp-unique names that are never on the curated list, so they always take
 * the free-form path: search the picker, choose "Add … as a custom language…", then fill the
 * Name/Code/level/vowel fields. Code is filled before the vowel-marks flag flips its label.
 */
async function addLanguage(
  page: Page,
  opts: { name: string; code?: string; band?: string; vowelized?: boolean },
): Promise<void> {
  // `exact` so this is the picker's "Language" combobox, not the header "Active language" one
  // (Playwright's accessible-name match is a substring by default).
  await page
    .getByRole('combobox', { name: 'Language', exact: true })
    .fill(opts.name);
  await page.getByRole('option', { name: /as a custom language/ }).click();
  await page.getByLabel('Name').fill(opts.name);
  if (opts.code !== undefined) {
    // Label is "Code (optional)" until "Include vowel marks" is checked (then it becomes "Code").
    await page.getByLabel('Code (optional)').fill(opts.code);
  }
  if (opts.band !== undefined) {
    await page.getByLabel('Starting level').selectOption(opts.band);
  }
  if (opts.vowelized) {
    await page.getByRole('checkbox', { name: /Include vowel marks/ }).check();
  }
  await page.getByRole('button', { name: 'Add language' }).click();
}

/**
 * Generate one sentence for a single timestamp-unique word and save the resulting cards.
 *
 * 429/503-tolerant: after pressing Generate we wait for EITHER the "Review & save" panel (success)
 * OR a cost-guard / transient-error panel; the latter is an acceptable outcome, so we return `false`
 * and skip the save. Returns `true` only when cards were actually saved.
 */
async function generateAndSave(page: Page, word: string): Promise<boolean> {
  await navigateTo(page, 'Generate');
  // `exact` so the textarea isn't confused with the "Parsed entries" chip list.
  await page.getByLabel('Words', { exact: true }).fill(word);
  const generateBtn = page.getByRole('button', { name: 'Generate' });
  await expect(generateBtn).toBeEnabled();
  await generateBtn.click();

  const saveBtn = page.getByRole('button', { name: /^Save \d+ sentences?$/ });
  // The cost guard fires the shared daily-limit panel (role="status") or a friendly LlmErrorState
  // (role="alert") for rate-limit / server-busy / generic — any of these is an ACCEPTABLE outcome.
  const guard = page
    .getByTestId('daily-limit-panel')
    .or(page.getByRole('alert'));
  await expect(saveBtn.or(guard).first()).toBeVisible({ timeout: LLM_TIMEOUT });
  if (!(await saveBtn.isVisible())) {
    return false; // cost guard / transient LLM error — correct behaviour, not a failure.
  }

  await saveBtn.click();
  await expect(page.getByText(/Saved \d+ cards?/)).toBeVisible();
  return true;
}

/**
 * Walk the current Review batch FORWARD, grading every card "Again" (never depletes the deck).
 *
 * On a production card (when `tapWord`) it reveals the tappable answer, taps a word to open the
 * explain popover, then closes it (structure only — never its LLM content, so a throttled `/explain`
 * can't fail this). Stops at the SessionComplete / empty state — it never asserts returning to a
 * prior card (review is forward-only).
 */
async function walkReviewGradingAgain(
  page: Page,
  opts: { tapWord?: boolean; maxCards?: number } = {},
): Promise<void> {
  const { tapWord = false, maxCards = 4 } = opts;
  const reveal = revealButton(page);
  // SessionComplete renders "Done for today" via <CardTitle> (a <div>, NOT a heading); its unique,
  // role-stable marker is the "Check for more" button — use that to detect the end-of-batch state.
  const done = page.getByRole('button', { name: 'Check for more' });
  const empty = page.getByTestId('empty-state');

  for (let i = 0; i < maxCards; i += 1) {
    // Wait for the previous grade to settle into the next card (or the end-of-batch state).
    await expect(reveal.or(done).or(empty).first()).toBeVisible();
    if (!(await reveal.isVisible())) {
      break; // SessionComplete ("Done for today") or empty batch — the forward-only walk is over.
    }

    const production = await page
      .getByRole('button', { name: 'Show answer' })
      .isVisible();
    await reveal.click();
    const answer = page.getByTestId('card-answer');
    await expect(answer).toBeVisible();

    if (production && tapWord) {
      // Each word of a production answer is a button[aria-haspopup="dialog"]; tapping opens the
      // explain popover. We assert it opens + closes only — never its (LLM) content.
      const words = answer.locator('button[aria-haspopup="dialog"]');
      if ((await words.count()) > 0) {
        await words.first().click();
        const popover = page.getByTestId('word-popover');
        await expect(popover).toBeVisible();
        await page.getByRole('button', { name: 'Close explanation' }).click();
        await expect(popover).toBeHidden();
      }
    }

    // Grade ONLY "Again" (data-rating="1") — keeps the card due (no depletion) and advances the walk.
    await page.locator('button[data-rating="1"]').click();
  }
}

/**
 * Permanently delete the signed-in account through the confirm-typed dialog (the lifecycle's
 * terminal, irreversible step — safe here because every user is a throwaway).
 *
 * The trigger and the in-dialog confirm both read "Delete account", so the confirm is scoped to the
 * dialog. A partial-failure 502 leaves the dialog open with a retryable `role="alert"`; per
 * SYNTHESIS Blocker 7.6 nothing was deleted server-side, so we retry exactly once and accept it.
 * Success tears down the local session and redirects to /login.
 */
async function deleteAccount(page: Page): Promise<void> {
  await navigateTo(page, 'Account');
  // Only the trigger exists at this point, so this is unambiguous; the dialog adds a second
  // "Delete account" button, which is why every later reference is dialog-scoped.
  await page.getByRole('button', { name: 'Delete account' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel(/Type .* to confirm/).fill(DELETE_CONFIRM_PHRASE);
  const confirm = dialog.getByRole('button', { name: 'Delete account' });
  await expect(confirm).toBeEnabled();
  await confirm.click();

  const loginHeading = page.getByRole('heading', { name: /log in/i });
  const retryableError = dialog.getByRole('alert');
  // Success → redirect to /login; a 502 partial → the dialog stays open with a retryable error.
  await expect(loginHeading.or(retryableError).first()).toBeVisible({
    timeout: 30_000,
  });
  if (await retryableError.isVisible()) {
    // 502 partial — retry exactly once (nothing was deleted server-side, so a retry is safe).
    await confirm.click();
    await expect(loginHeading).toBeVisible({ timeout: 30_000 });
  }
  await expect(page).toHaveURL(/\/login/);
}

test.describe('fresh users learn two languages end-to-end, then delete their accounts', () => {
  // The admin API is the ONLY way to mint a usable confirmed user; without its secret there is
  // nothing to drive, so the whole group is skipped (a Tier A run stays green).
  test.skip(
    !adminConfigured(),
    'SUPABASE_STAGING_SERVICE_ROLE_KEY not set — Tier A run',
  );
  // Run the users one-at-a-time so this file never has more than one fresh real-LLM user in flight.
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async () => {
    for (let i = 0; i < USER_COUNT; i += 1) {
      createdUsers.push(await createConfirmedUser());
    }
  });

  test.afterAll(async () => {
    // Defense-in-depth: the lifecycle's UI delete should already have removed each user, but a test
    // that failed before that step would leak one. Hard-delete every created id (404-tolerant, so a
    // user already gone via the UI is a no-op) — guaranteeing zero leaked `auth.users`.
    for (const user of createdUsers) {
      try {
        await deleteUser(user.id);
      } catch {
        // Best-effort cleanup: never let a cleanup failure mask a real test result.
      }
    }
  });

  for (let userIndex = 0; userIndex < USER_COUNT; userIndex += 1) {
    test(`fresh user ${userIndex + 1} completes the two-language lifecycle then deletes the account`, async ({
      page,
    }, testInfo) => {
      // A long, multi-screen journey with optional real-Groq round-trips; give it room past 90s.
      test.slow();

      const user = createdUsers[userIndex];
      if (!user) {
        throw new Error(`fresh user ${userIndex + 1} was not provisioned`);
      }
      const stamp = `${Date.now()}${userIndex}`;
      const langA = `ZZlc-A-${stamp}`; // non-RTL throwaway
      const langB = `ZZlc-he-${stamp}`; // RTL Hebrew throwaway (code "he" + vowel marks)

      await test.step('Log in as the fresh admin-created user', async () => {
        await loginAs(page, user);
      });

      await test.step(`Add language A (${langA}) starting at CEFR B1`, async () => {
        await navigateTo(page, 'Languages');
        await addLanguage(page, { name: langA, band: 'B1' });
        // The new row exposes a "Remove <name>" control and A is auto-selected active.
        await expect(
          page.getByRole('button', { name: `Remove ${langA}` }),
        ).toBeVisible();
      });

      await test.step('Confirm language A shows CEFR band B1', async () => {
        // The sidebar level panel reflects the non-A1 starting band (its follow-up PUT /proficiency).
        await expect(page.getByTestId('cefr-band')).toHaveText('B1', {
          timeout: 30_000,
        });
      });

      await test.step(`Add language B (${langB}) — Hebrew (code "he") + vowel marks (RTL)`, async () => {
        await navigateTo(page, 'Languages');
        await addLanguage(page, { name: langB, code: 'he', vowelized: true });
        await expect(
          page.getByRole('button', { name: `Remove ${langB}` }),
        ).toBeVisible();
      });

      await test.step('Switch between A and B — the CEFR band flips per language', async () => {
        const cefrBand = page.getByTestId('cefr-band');
        // Neither language has been reviewed yet, so each sits exactly at its starting band.
        await switchActiveLanguage(page, langA);
        await expect(cefrBand).toHaveText('B1', { timeout: 30_000 });
        await switchActiveLanguage(page, langB);
        await expect(cefrBand).toHaveText('A1', { timeout: 30_000 });
      });

      await test.step('With B active, assert RTL + the vowel-marks switch toggles', async () => {
        await navigateTo(page, 'Review');
        const content = page.getByTestId('review-content');
        await expect(content).toHaveAttribute('dir', 'rtl');

        // The vowel-marks switch renders only for a vowelized language; toggling flips aria-checked.
        // Its accessible name is the language-aware visible label ("Vowel marks (nikkud)" /
        // "(harakat)"), so match on the stable prefix.
        const vowelSwitch = page.getByRole('switch', {
          name: /^Vowel marks/,
        });
        await expect(vowelSwitch).toBeVisible();
        const before =
          (await vowelSwitch.getAttribute('aria-checked')) ?? 'true';
        await vowelSwitch.click();
        await expect(vowelSwitch).not.toHaveAttribute('aria-checked', before);
        await vowelSwitch.click(); // restore the device-wide preference to as-found.
        await expect(vowelSwitch).toHaveAttribute('aria-checked', before);
      });

      let savedA = false;
      await test.step('Generate + save a card for A (LLM-gated, 429/503-tolerant)', async () => {
        if (!INCLUDE_LLM) {
          testInfo.annotations.push({
            type: 'skip',
            description:
              'STAGING_INCLUDE_LLM unset — skipping generate/save for A',
          });
          return;
        }
        // A is the only language we generate for (≤1 generate/user keeps us under the day-0 cap of 5).
        await switchActiveLanguage(page, langA);
        savedA = await generateAndSave(page, `zz${stamp}a`);
      });

      await test.step('Study A — reveal, tap-a-word, grade "Again" (LLM-gated)', async () => {
        if (!INCLUDE_LLM || !savedA) {
          testInfo.annotations.push({
            type: 'skip',
            description:
              'No saved A cards (LLM off or cost guard) — skipping A review',
          });
          return;
        }
        await navigateTo(page, 'Review');
        await walkReviewGradingAgain(page, { tapWord: true });
      });

      await test.step('Discover new words (LLM-gated, 429/503-tolerant)', async () => {
        if (!INCLUDE_LLM) {
          testInfo.annotations.push({
            type: 'skip',
            description: 'STAGING_INCLUDE_LLM unset — skipping Discover',
          });
          return;
        }
        await navigateTo(page, 'Discover');
        await page.getByLabel('How many words').fill('3'); // within the 1..20 schema bound
        await page.getByLabel('Topic (optional)').fill('food');
        const discoverBtn = page.getByRole('button', { name: 'Discover' });
        await expect(discoverBtn).toBeEnabled();
        await discoverBtn.click();

        const suggestions = page.getByTestId('discover-suggestions');
        const guard = page
          .getByTestId('daily-limit-panel')
          .or(page.getByRole('alert'));
        const noWords = page.getByText('No new words found');
        // Success (a suggestion list), a cost-guard panel, or a "no new words" empty state — all OK.
        await expect(suggestions.or(guard).or(noWords).first()).toBeVisible({
          timeout: LLM_TIMEOUT,
        });
        if (await suggestions.isVisible()) {
          await expect(suggestions.getByRole('listitem').first()).toBeVisible();
        }
      });

      await test.step('Settings — edit the Discover word count and Save', async () => {
        await navigateTo(page, 'Settings');
        const countField = page.getByLabel('Discover word count');
        await expect(countField).toBeVisible();
        const original = (await countField.inputValue()).trim();
        const edited = original === '5' ? '6' : '5'; // a different in-bounds value (1..20)
        await countField.fill(edited);
        await page.getByRole('button', { name: 'Save settings' }).click();
        await expect(page.getByText('Settings saved').first()).toBeVisible();
      });

      await test.step('Account — the signed-in email is shown', async () => {
        await navigateTo(page, 'Account');
        await expect(page.getByTestId('account-email')).toContainText('@');
      });

      await test.step('Sign out → redirected to /login', async () => {
        // The header UserMenu sign-out (scoped to the banner so it is unambiguous vs. the page one).
        await page
          .getByRole('banner')
          .getByRole('button', { name: 'Sign out' })
          .click();
        await expect(page).toHaveURL(/\/login/);
        await expect(
          page.getByRole('heading', { name: /log in/i }),
        ).toBeVisible();
      });

      await test.step('Log back in → languages (and their decks) survived', async () => {
        await loginAs(page, user);
        // Both languages persisted across the logout/login, proving the account's data survived.
        await navigateTo(page, 'Languages');
        await expect(
          page.getByRole('button', { name: `Remove ${langA}` }),
        ).toBeVisible();
        await expect(
          page.getByRole('button', { name: `Remove ${langB}` }),
        ).toBeVisible();
      });

      await test.step('Delete the account → land on /login (cascade erases all data)', async () => {
        await deleteAccount(page);
      });
    });
  }
});
