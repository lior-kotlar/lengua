import { expect, login, test, type Page } from './fixtures';

/**
 * Layer A — the full end-to-end happy-path journey as the seeded DEMO user (staging re-validation).
 *
 * One sequential, stateful test (a journey, not isolated cases) walks SYNTHESIS Blocker-4 steps
 * 1–21: log in → add a throwaway language A (non-RTL, level B1) → confirm its CEFR band → generate
 * + save + study A → add a throwaway RTL Hebrew language B → switch between A and B (the CEFR band
 * flips per language) → assert B renders right-to-left and the vowel-marks switch toggles → generate
 * + save + study B → Discover → Settings → Account → sign out → log back in. The destructive step 22
 * (delete account) is deliberately NOT here — it belongs only to the fresh-user driver.
 *
 * Guardrails baked in (VALIDATION-PLAN §5), since this runs against the SHARED demo account:
 *  - Anti-pollution: it never adds a literal "Spanish"/"Hebrew" (those would duplicate the seeded
 *    deck); it creates UNIQUELY-NAMED throwaway languages and REMOVES both in a `finally` so the
 *    account is left exactly as found (cascade-delete takes their cards with them).
 *  - Review grades ONLY "Again" (data-rating="1") so the deck is never depleted, and the walk is
 *    FORWARD-ONLY (it never asserts returning to a prior card).
 *  - Every LLM-touching sub-step (generate / save / review tap-a-word / discover) is gated behind
 *    STAGING_INCLUDE_LLM and is 429/503-TOLERANT: a fired cost guard renders a friendly panel, which
 *    we treat as an acceptable PASS and skip the rest of that sub-step. Structure/read-only
 *    assertions (add/switch language, CEFR band, RTL, settings, account, auth) always run.
 *  - Words for generate are tiny + timestamp-unique; combined with per-run throwaway languages they
 *    can never collide with the shared deck.
 *
 * Runs ONLY via `playwright.staging.config.ts` (`pnpm test:e2e-staging`), never in CI. See
 * `fixtures.ts` for the shared `login` helper + consent pre-dismissal.
 */

/** Only fire the (quota-bounded, real-Groq) LLM sub-steps when explicitly opted in. */
const INCLUDE_LLM = Boolean(process.env.STAGING_INCLUDE_LLM);

/** Generous budget for a real `/generate` or `/discover` (cold Cloud Run + real Groq are slow). */
const LLM_TIMEOUT = 60_000;

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
 * explain popover, then closes it. With `scriptFont` set it asserts the script-font element renders
 * once a card is revealed (the RTL proof for Hebrew). Stops at the SessionComplete / empty state —
 * it never asserts returning to a prior card (review is forward-only).
 */
async function walkReviewGradingAgain(
  page: Page,
  opts: { tapWord?: boolean; scriptFont?: string; maxCards?: number } = {},
): Promise<void> {
  const { tapWord = false, scriptFont, maxCards = 4 } = opts;
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

    if (scriptFont !== undefined && i === 0) {
      // The revealed card carries target-language text in its script-correct font (RTL proof).
      await expect(
        page.getByTestId('review-content').locator(`.${scriptFont}`).first(),
      ).toBeVisible();
    }

    if (production && tapWord) {
      // Each word of a production answer is a button[aria-haspopup="dialog"]; tapping opens the
      // explain popover. We assert it opens + closes (structure only) — never its (LLM) content, so
      // a throttled `/explain` can't fail this step.
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

/** Open the Languages screen, re-authenticating first if the session has already been torn down. */
async function gotoLanguages(page: Page): Promise<void> {
  await page.goto('/languages');
  if (/\/login/.test(page.url())) {
    await login(page);
    await page.goto('/languages');
  }
  await expect(page.getByRole('heading', { name: 'Languages' })).toBeVisible();
}

/** Best-effort cleanup: remove a throwaway language by name if it is still present. */
async function removeLanguageIfPresent(
  page: Page,
  name: string,
): Promise<void> {
  try {
    await gotoLanguages(page);
    const trigger = page.getByRole('button', { name: `Remove ${name}` });
    // The languages list loads async (a separate query), so a fresh navigation momentarily shows zero
    // rows. Wait for the row to appear before deciding it is absent — checking count() immediately
    // races the load and silently skips (leaks) a language that is actually present. A genuine,
    // sustained absence (already removed) falls through the timeout to a graceful return.
    try {
      await expect(trigger.first()).toBeVisible({ timeout: 15_000 });
    } catch {
      return; // genuinely not present (already removed) — nothing to clean up.
    }
    await trigger.first().click();
    // The mutation fires only from the in-dialog "Remove" (the trigger merely opened the dialog).
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
    await expect(
      page.getByRole('button', { name: `Remove ${name}` }),
    ).toHaveCount(0);
  } catch {
    // Cleanup is best-effort: a failure here must never mask the test's own result.
  }
}

test('demo user completes the full learning journey across two languages', async ({
  page,
}, testInfo) => {
  // A long, multi-screen journey with several real-Groq round-trips; give it room past the 90s default.
  test.slow();

  const stamp = Date.now();
  const langA = `ZZval-A-${stamp}`; // non-RTL throwaway
  const langB = `ZZval-he-${stamp}`; // RTL Hebrew throwaway (code "he" + vowel marks)
  const created: string[] = [];

  try {
    await test.step('Log in as the seeded demo user', async () => {
      await login(page);
    });

    await test.step(`Add throwaway language A (${langA}) starting at CEFR B1`, async () => {
      await navigateTo(page, 'Languages');
      await addLanguage(page, { name: langA, band: 'B1' });
      created.push(langA);
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

    await test.step(`Add throwaway language B (${langB}) — Hebrew (code "he") + vowel marks (RTL)`, async () => {
      await navigateTo(page, 'Languages');
      await addLanguage(page, { name: langB, code: 'he', vowelized: true });
      created.push(langB);
      await expect(
        page.getByRole('button', { name: `Remove ${langB}` }),
      ).toBeVisible();
    });

    await test.step('Switch between A and B — the CEFR band flips per language', async () => {
      const cefrBand = page.getByTestId('cefr-band');
      await switchActiveLanguage(page, langA);
      // A was created at B1; any "Again" reviews above can only nudge it down to A2 — never to A1.
      await expect(cefrBand).toHaveText(/^(A2|B1)$/, { timeout: 30_000 });
      const bandA = (await cefrBand.textContent())?.trim();
      await switchActiveLanguage(page, langB);
      // B is freshly created and unreviewed → its default A1 band.
      await expect(cefrBand).toHaveText('A1', { timeout: 30_000 });
      expect(bandA).not.toBe('A1'); // the band genuinely differs per language.
    });

    await test.step('With B active, assert RTL + the vowel-marks switch toggles', async () => {
      await navigateTo(page, 'Review');
      const content = page.getByTestId('review-content');
      await expect(content).toHaveAttribute('dir', 'rtl');

      // The vowel-marks switch renders only for a vowelized language; toggling it flips aria-checked.
      const vowelSwitch = page.getByRole('switch', {
        name: 'Show vowel marks',
      });
      await expect(vowelSwitch).toBeVisible();
      const before = (await vowelSwitch.getAttribute('aria-checked')) ?? 'true';
      await vowelSwitch.click();
      await expect(vowelSwitch).not.toHaveAttribute('aria-checked', before);
      await vowelSwitch.click(); // restore the device-wide preference to as-found.
      await expect(vowelSwitch).toHaveAttribute('aria-checked', before);
    });

    let savedB = false;
    await test.step('Generate + save a card for B (LLM-gated, 429/503-tolerant)', async () => {
      if (!INCLUDE_LLM) {
        testInfo.annotations.push({
          type: 'skip',
          description:
            'STAGING_INCLUDE_LLM unset — skipping generate/save for B',
        });
        return;
      }
      savedB = await generateAndSave(page, `zz${stamp}b`);
    });

    await test.step('Study B — RTL Hebrew font, tap-a-word, grade "Again" (LLM-gated)', async () => {
      if (!INCLUDE_LLM || !savedB) {
        testInfo.annotations.push({
          type: 'skip',
          description:
            'No saved B cards (LLM off or cost guard) — skipping B review',
        });
        return;
      }
      await navigateTo(page, 'Review');
      await walkReviewGradingAgain(page, {
        tapWord: true,
        scriptFont: 'font-hebrew',
      });
    });

    await test.step('Discover new words for B (LLM-gated, 429/503-tolerant)', async () => {
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

      // Restore the demo account's original value so we leave Settings exactly as found.
      await countField.fill(original);
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

    await test.step('Log back in → Dashboard (decks + languages persist)', async () => {
      await login(page);
    });
  } finally {
    // Cleanup: remove BOTH throwaway languages (cascade removes their cards) so the shared demo
    // account is left exactly as found — even if the journey above failed partway through.
    for (const name of created) {
      await removeLanguageIfPresent(page, name);
    }
  }
});
