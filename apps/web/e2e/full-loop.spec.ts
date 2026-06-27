import { expect, test, type Page } from './fixtures';

/**
 * Full core-loop E2E — the Phase-4 exit-gate proof (box 1).
 *
 * A signed-in browser user runs the ENTIRE loop end-to-end against the FastAPI backend with NO
 * Streamlit involved, in ONE session:
 *
 *   login (seeded demo) → Generate words → save → Review (reveal + grade) → Discover preview
 *
 * The per-screen behaviour is each covered in depth by its own group spec
 * (generate/review/discover/auth); this spec deliberately composes all four to prove they form the
 * full loop. Runs against the seeded demo account on the ephemeral stack (Supabase + the API
 * container with LLM_PROVIDER=fake). Every LLM-backed step here goes through the REAL server seam —
 * nothing is browser-stubbed — so it is a genuine end-to-end walk. The zero-real-LLM guarantee
 * holds: the API container ships no Groq/Gemini keys and the FakeLLM does no I/O (CI asserts the
 * FakeLLM call counter separately).
 *
 * Determinism + no-deplete: the generated words are timestamp-unique so they never collide with the
 * seeded deck, and the single Review grade uses "Again" (FSRS keeps the card due) so repeated CI
 * runs never deplete the shared demo deck. Gated on E2E_STACK=1 like the other authed flows; the
 * active language defaults to the seeded Spanish deck (no language switch here).
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

/** The reveal button for whichever card is up (production = "Show answer", recognition = the other). */
function revealButton(page: Page) {
  return page.getByRole('button', { name: /^Show (answer|translation)$/ });
}

test.describe('full core loop (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('generate → save → review (reveal + grade) → discover, no Streamlit', async ({
    page,
  }) => {
    // Timestamp-unique so the generated cards never collide with the seeded demo deck.
    const stamp = Date.now();
    const wordA = `gamma${stamp}`;
    const wordB = `delta${stamp}`;

    await login(page);

    // ── 1. GENERATE ──────────────────────────────────────────────────────────────────────────
    await navigateTo(page, 'Generate');
    const generateButton = page.getByRole('button', { name: 'Generate' });
    await expect(generateButton).toBeDisabled();
    // `exact` so the textarea isn't confused with the "Parsed entries" chip list.
    await page.getByLabel('Words', { exact: true }).fill(`${wordA}\n${wordB}`);
    await expect(generateButton).toBeEnabled();
    await generateButton.click();

    // The deterministic FakeLLM renders one sentence per word; its translation is the language-
    // agnostic "This is a sentence with <word>." (the target sentence carries a `[Spanish:…]`
    // prefix, so `exact` matches the translation row).
    await expect(
      page.getByText(`This is a sentence with ${wordA}.`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`This is a sentence with ${wordB}.`, { exact: true }),
    ).toBeVisible();

    // ── 2. SAVE (all selected by default → two sentences = four cards) ─────────────────────────
    await page.getByRole('button', { name: /save 2 sentences/i }).click();
    await expect(page.getByText('Cards saved')).toBeVisible();
    await expect(page.getByText('Saved 4 cards')).toBeVisible();

    // ── 3. REVIEW (reveal + grade Again) ──────────────────────────────────────────────────────
    // The saved cards are immediately due (the generate flow invalidates the review cache), so the
    // active language's batch is non-empty here.
    await navigateTo(page, 'Review');
    const counts = page.getByTestId('review-counts');
    await expect(counts).toContainText('new');
    await expect(counts).toContainText('due');

    await expect(revealButton(page)).toBeVisible();
    await revealButton(page).click();
    // The four rating buttons surface only after reveal.
    for (const label of ['Again', 'Hard', 'Good', 'Easy']) {
      await expect(
        page.getByRole('button', { name: new RegExp(`^${label}`) }),
      ).toBeVisible();
    }
    // Grade with "Again" (keeps the demo deck due) → advances to the next card.
    await page.getByRole('button', { name: /^Again/ }).click();
    await expect(revealButton(page)).toBeVisible();

    // ── 4. DISCOVER (preview suggested new words) ─────────────────────────────────────────────
    await navigateTo(page, 'Discover');
    await page.getByRole('button', { name: 'Discover' }).click();
    const suggestions = page.getByTestId('discover-suggestions');
    await expect(suggestions).toBeVisible();
    // The FakeLLM walks a fixed English pool; "house" is always present (the demo Spanish words and
    // the generated gamma/delta words are not in that pool, so nothing excludes it).
    await expect(suggestions.getByText('house', { exact: true })).toBeVisible();
  });
});
