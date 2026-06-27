import { expect, test, type Page } from './fixtures';

/**
 * Review screen E2E (group 4.6) — runs against the seeded demo account on the ephemeral stack
 * (Supabase + the API container with LLM_PROVIDER=fake). The demo deck has saved, due cards
 * (recognition + production pairs), so Review always has something to show. The deterministic
 * FakeLLM returns a fixed explanation ("<word>: a N-letter word used in this sentence.") for any
 * tapped word, so the tap-a-word assertion is stable. The zero-real-LLM guarantee holds: the API
 * container has no Groq/Gemini keys (CI asserts the FakeLLM counter separately).
 *
 * Grading uses "Again" throughout: it keeps the graded card due (FSRS reschedules it minutes out),
 * so this spec doesn't deplete the shared demo deck over repeated CI runs.
 *
 * Gated on E2E_STACK=1 like the other authed flows.
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

async function gotoReview(page: Page) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Review' })
    .click();
  await expect(page.getByRole('heading', { name: 'Review' })).toBeVisible();
}

/** The reveal button for whichever card is up (production = "Show answer", recognition = other). */
function revealButton(page: Page) {
  return page.getByRole('button', { name: /^Show (answer|translation)$/ });
}

test.describe('review screen (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('shows the counts header, reveals a card, and grades via mouse + keyboard', async ({
    page,
  }) => {
    await login(page);
    await gotoReview(page);

    // 4.6.1 — the new/due counts header and the first card's reveal control render.
    const counts = page.getByTestId('review-counts');
    await expect(counts).toContainText('new');
    await expect(counts).toContainText('due');
    await expect(revealButton(page)).toBeVisible();

    // 4.6.2 — revealing surfaces all four rating buttons (hidden before).
    await expect(page.getByRole('button', { name: /^Again/ })).toHaveCount(0);
    await revealButton(page).click();
    for (const label of ['Again', 'Hard', 'Good', 'Easy']) {
      await expect(
        page.getByRole('button', { name: new RegExp(`^${label}`) }),
      ).toBeVisible();
    }

    // 4.6.3 — grading advances to the next card (a fresh reveal control appears).
    await page.getByRole('button', { name: /^Again/ }).click();
    await expect(revealButton(page)).toBeVisible();

    // 4.6.5 — reveal + grade the next card using only the keyboard.
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', { name: /^Good/ })).toBeVisible();
    await page.keyboard.press('1'); // Again
    await expect(revealButton(page)).toBeVisible();
  });

  test('opens a tap-a-word explanation popover on a production card', async ({
    page,
  }) => {
    await login(page);
    await gotoReview(page);

    // 4.6.4 — walk to a production card (grade recognition cards with Again to advance), then tap
    // a word in the revealed target sentence and assert the explanation popover.
    let onProduction = false;
    for (let i = 0; i < 12 && !onProduction; i += 1) {
      await expect(revealButton(page)).toBeVisible();
      const showAnswer = page.getByRole('button', { name: 'Show answer' });
      if (await showAnswer.isVisible()) {
        await showAnswer.click();
        onProduction = true;
        break;
      }
      // A recognition card — reveal and grade it to move on.
      await page.getByRole('button', { name: 'Show translation' }).click();
      await page.getByRole('button', { name: /^Again/ }).click();
    }
    expect(onProduction).toBe(true);

    // Tap the first word of the target sentence; the popover shows the FakeLLM explanation.
    const answer = page.getByTestId('card-answer');
    await answer.getByRole('button').first().click();

    const popover = page.getByTestId('word-popover');
    await expect(popover).toBeVisible();
    await expect(popover).toContainText('used in this sentence');
  });
});
