import { expect, test, type Page } from './fixtures';

/**
 * RTL, diacritics & complex-scripts E2E (group 4.9) — runs against the seeded demo account on the
 * ephemeral stack (Supabase + the API container with LLM_PROVIDER=fake). The seed provisions a
 * second, vowelized **Hebrew** language whose deck carries real nikkud (recognition + production
 * pairs), so this spec can prove, end-to-end:
 *
 *  - 4.9.1 per-language direction — the Review content region is `dir="rtl"` for Hebrew;
 *  - 4.9.2 diacritic-correct font — the self-hosted "Noto Sans Hebrew" is loaded (`document.fonts`)
 *          and the rendered sentence carries nikkud (no tofu); a screenshot is attached as the
 *          visual snapshot;
 *  - 4.9.3 vowel-marks toggle — flipping it strips/restores the nikkud in the rendered text;
 *  - 4.9.4 RTL-aware tap-a-word — tapping a word mid-sentence (touch AND click) opens that word's
 *          explanation, and tapping a different word switches to it.
 *
 * The deterministic FakeLLM returns a fixed explanation for any tapped word, and the API container
 * has no Groq/Gemini keys, so the zero-real-LLM guarantee holds (CI asserts the FakeLLM counter
 * separately). Grading uses "Again" so the shared demo deck is never depleted. Gated on E2E_STACK=1.
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

// Any Hebrew vowel point (nikkud) / cantillation mark — the exact set `stripDiacritics` removes
// (lib/language-text.ts), so "stripped" text contains none of these.
const NIKKUD = /[֑-ׇֽֿׁׂׅׄ]/u;

function hasNikkud(text: string | null): boolean {
  return text !== null && NIKKUD.test(text);
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

/** Switch the header picker to the seeded vowelized Hebrew language, then open Review. */
async function gotoHebrewReview(page: Page) {
  await page.getByLabel('Active language').selectOption({ label: 'Hebrew' });
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Review' })
    .click();
  await expect(page.getByRole('heading', { name: 'Review' })).toBeVisible();
}

/** The reveal button of whichever card is up. */
function revealButton(page: Page) {
  return page.getByRole('button', { name: /^Show (answer|translation)$/ });
}

/** Walk (grading Again) until a recognition card is up — its Hebrew prompt is then visible. */
async function walkToRecognition(page: Page) {
  for (let i = 0; i < 12; i += 1) {
    await expect(revealButton(page)).toBeVisible();
    if (
      await page.getByRole('button', { name: 'Show translation' }).isVisible()
    ) {
      return;
    }
    // A production card — reveal + grade Again to advance.
    await page.getByRole('button', { name: 'Show answer' }).click();
    await page.getByRole('button', { name: /^Again/ }).click();
  }
  throw new Error('no recognition card found in the Hebrew deck');
}

/** Walk (grading Again) until a production card is up, then reveal its tappable Hebrew sentence. */
async function walkToProductionRevealed(page: Page) {
  for (let i = 0; i < 12; i += 1) {
    await expect(revealButton(page)).toBeVisible();
    const showAnswer = page.getByRole('button', { name: 'Show answer' });
    if (await showAnswer.isVisible()) {
      await showAnswer.click();
      return;
    }
    // A recognition card — reveal + grade Again to advance.
    await page.getByRole('button', { name: 'Show translation' }).click();
    await page.getByRole('button', { name: /^Again/ }).click();
  }
  throw new Error('no production card found in the Hebrew deck');
}

test.describe('RTL, diacritics & vowel marks (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('renders RTL in a diacritic-correct font and the vowel-marks toggle strips/restores nikkud', async ({
    page,
  }, testInfo) => {
    await login(page);
    await gotoHebrewReview(page);

    // 4.9.1 — the content region mirrors to right-to-left for the Hebrew language.
    const content = page.getByTestId('review-content');
    await expect(content).toHaveAttribute('dir', 'rtl');

    // A recognition card shows its Hebrew prompt (with nikkud) without revealing.
    await walkToRecognition(page);
    const hebrew = content.locator('.font-hebrew').first();
    await expect(hebrew).toBeVisible();

    // 4.9.2 — the self-hosted Hebrew font is actually loaded (no fallback / tofu)…
    const fontLoaded = await page.evaluate(async () => {
      await document.fonts.ready;
      return document.fonts.check('16px "Noto Sans Hebrew"');
    });
    expect(fontLoaded).toBe(true);
    // …the rendered prompt is in that font and carries nikkud.
    await expect(hebrew).toHaveClass(/font-hebrew/);
    expect(hasNikkud(await hebrew.textContent())).toBe(true);
    // Visual snapshot for human review (mirrored layout + diacritics on base letters).
    await testInfo.attach('review-rtl-hebrew', {
      body: await page.screenshot(),
      contentType: 'image/png',
    });

    // 4.9.3 — toggling vowel marks OFF strips the nikkud from the rendered text…
    const toggle = page.getByRole('switch', { name: 'Show vowel marks' });
    await toggle.click();
    await expect
      .poll(async () => hasNikkud(await hebrew.textContent()))
      .toBe(false);
    // …and toggling back ON restores them.
    await toggle.click();
    await expect
      .poll(async () => hasNikkud(await hebrew.textContent()))
      .toBe(true);
  });
});

test.describe('RTL-aware tap-a-word (touch + click)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );
  // Emulate a touch device so `.tap()` exercises the touch path alongside `.click()` (4.9.4).
  test.use({ hasTouch: true });

  test('tapping a word mid-RTL-sentence opens the correct explanation', async ({
    page,
  }) => {
    await login(page);
    await gotoHebrewReview(page);
    await walkToProductionRevealed(page);

    const answer = page.getByTestId('card-answer');
    // Only the tappable WORD buttons (each has aria-haspopup="dialog") — this deliberately excludes
    // the popover's "Close" button, which would otherwise shift the indices once a popover is open.
    const words = answer.locator('button[aria-haspopup="dialog"]');
    await expect(words.first()).toBeVisible();
    // The seeded Hebrew production sentences all have at least three words.
    expect(await words.count()).toBeGreaterThanOrEqual(3);

    // TOUCH: tap a word mid-sentence (not the first) → its explanation popover opens.
    await words.nth(1).tap();
    const popover = page.getByTestId('word-popover');
    await expect(popover).toBeVisible();
    await expect(popover).toContainText('used in this sentence');
    const firstLabel = await popover.getAttribute('aria-label');

    // CLICK: a different mid-sentence word switches to ITS explanation (correct word boundaries).
    await words.nth(2).click();
    await expect(popover).toBeVisible();
    await expect(popover).toContainText('used in this sentence');
    const secondLabel = await popover.getAttribute('aria-label');
    expect(secondLabel).not.toBe(firstLabel);
  });
});
