import { expect, test, type Page } from './fixtures';

/**
 * Discover screen E2E (group 4.7) — runs against the seeded demo account on the ephemeral stack
 * (Supabase + the API container with LLM_PROVIDER=fake). The deterministic FakeLLM walks a fixed
 * English vocabulary pool (skipping words the learner already knows), so the real-stack preview is
 * stable. Reroll + accept + the quota-429 path are stubbed at the BROWSER boundary so the assertions
 * are deterministic — the FakeLLM (and the backend's short-window reuse cache) would otherwise return
 * the SAME words for an identical reroll, and the server LLM seam is never reached for the stubbed
 * cases. The zero-real-LLM guarantee holds: the API container has no Groq/Gemini keys (CI asserts the
 * FakeLLM counter separately). Gated on E2E_STACK=1 like the other authed flows.
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

async function gotoDiscover(page: Page) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Discover' })
    .click();
  await expect(page.getByRole('heading', { name: 'Discover' })).toBeVisible();
}

test.describe('discover screen (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('runs Discover against the FakeLLM and shows the suggested-words preview', async ({
    page,
  }) => {
    await login(page);
    await gotoDiscover(page);

    // 4.7.1 — the count defaults to the user's discover-count setting; the demo account has none
    // saved, so it falls back to the server default (5).
    await expect(page.getByLabel('How many words')).toHaveValue('5');

    await page.getByRole('button', { name: 'Discover' }).click();

    // The deterministic FakeLLM previews words from its fixed pool (the demo deck's Spanish words
    // aren't in the English pool, so nothing is excluded) — "house" is always first.
    const suggestions = page.getByTestId('discover-suggestions');
    await expect(suggestions).toBeVisible();
    await expect(suggestions.getByText('house', { exact: true })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Use these words' }),
    ).toBeVisible();
  });

  test('rerolls to a fresh set and accepts the words into the Generate flow', async ({
    page,
  }) => {
    await login(page);
    await gotoDiscover(page);

    // Stub /discover at the browser boundary so a reroll deterministically returns a NEW set.
    let call = 0;
    await page.route('**/discover', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      call += 1;
      const words =
        call === 1 ? ['uno', 'dos', 'tres'] : ['cuatro', 'cinco', 'seis'];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ words }),
      });
    });

    await page.getByRole('button', { name: 'Discover' }).click();
    await expect(page.getByText('uno', { exact: true })).toBeVisible();

    // 4.7.2 — rerolling replaces the old set with a fresh one.
    await page.getByRole('button', { name: 'Try different words' }).click();
    await expect(page.getByText('cuatro', { exact: true })).toBeVisible();
    await expect(page.getByText('uno', { exact: true })).toHaveCount(0);

    // 4.7.2 — accepting routes the words into the Generate flow with them prefilled (the generate
    // UI is reused, not duplicated).
    await page.getByRole('button', { name: 'Use these words' }).click();
    await expect(page.getByRole('heading', { name: 'Generate' })).toBeVisible();
    await expect(page.getByLabel('Words', { exact: true })).toHaveValue(
      'cuatro\ncinco\nseis',
    );
  });

  test('renders the shared daily-limit panel for a stubbed quota 429', async ({
    page,
  }) => {
    await login(page);
    await gotoDiscover(page);

    // Stub the discover endpoint at the browser boundary (the server LLM seam is never hit).
    await page.route('**/discover', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'daily_limit_reached',
          message: 'Daily limit reached, please try again tomorrow.',
        }),
      });
    });

    await page.getByRole('button', { name: 'Discover' }).click();

    // 4.7.3 — the dedicated shared daily-limit panel (the same one Generate uses), not a generic error.
    await expect(page.getByTestId('daily-limit-panel')).toBeVisible();
    await expect(page.getByText('Daily limit reached')).toBeVisible();
  });
});
