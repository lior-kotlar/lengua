import { expect, test, type Page } from './fixtures';

/**
 * Generate screen E2E (group 4.5) — runs against the seeded demo account on the ephemeral stack
 * (Supabase + the API container with LLM_PROVIDER=fake). The deterministic FakeLLM echoes each input
 * word back into a fixed sentence template, so the assertions below are stable. The zero-real-LLM
 * guarantee is preserved: the API container has no Groq/Gemini keys (the CI job asserts the FakeLLM
 * counter separately), and the daily-limit test stubs the API at the BROWSER boundary so the server
 * LLM seam is never reached. Gated on E2E_STACK=1 like the other authed flows.
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';
// The web bundle is built against this in CI; the API request fixture below calls it directly.
const API_BASE = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

async function gotoGenerate(page: Page) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Generate' })
    .click();
  await expect(page.getByRole('heading', { name: 'Generate' })).toBeVisible();
}

test.describe('generate screen (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('generate, select a subset, save, and the saved cards become reviewable', async ({
    page,
    request,
  }) => {
    // Unique per run so the assertions never collide with the seeded demo cards.
    const stamp = Date.now();
    const wordA = `alpha${stamp}`;
    const wordB = `beta${stamp}`;

    await login(page);
    await gotoGenerate(page);

    // 4.5.1 — the Generate button is disabled until words are entered, then enables.
    const generateButton = page.getByRole('button', { name: 'Generate' });
    await expect(generateButton).toBeDisabled();
    // `exact` so the textarea isn't confused with the "Parsed entries" chip list.
    await page.getByLabel('Words', { exact: true }).fill(`${wordA}\n${wordB}`);
    await expect(generateButton).toBeEnabled();

    // Capture the bearer token from the real generate call (the review check below reuses it). We
    // read the token from the request header rather than the body: the API client passes a Request
    // object to fetch, whose post body Playwright cannot always introspect.
    const genRequestPromise = page.waitForRequest(
      (req) => req.url().endsWith('/generate') && req.method() === 'POST',
    );
    await generateButton.click();
    const genRequest = await genRequestPromise;
    const authHeader = genRequest.headers()['authorization'];
    expect(authHeader).toMatch(/^Bearer /);

    // 4.5.2 — the deterministic FakeLLM sentences render with translations + used-word chips.
    // `exact` because the target sentence (`[Spanish:A1] This is a sentence with …`) contains the
    // translation as a substring — Playwright's getByText defaults to a substring match.
    await expect(
      page.getByText(`This is a sentence with ${wordA}.`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`This is a sentence with ${wordB}.`, { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(wordA, { exact: true })).toBeVisible();
    await expect(page.getByText(wordB, { exact: true })).toBeVisible();

    // 4.5.3 — deselect the second sentence; only the first should be saved.
    await page.getByRole('checkbox', { name: new RegExp(wordB) }).uncheck();
    await expect(page.getByText('1 of 2 selected')).toBeVisible();
    await page.getByRole('button', { name: /save 1 sentence/i }).click();

    // Success toast + the saved confirmation panel.
    await expect(page.getByText('Cards saved')).toBeVisible();
    await expect(page.getByText('Saved 2 cards')).toBeVisible();

    // The saved cards are now reviewable: the active language's due queue contains the first
    // sentence's word and NOT the deselected one. Hitting the API directly with the captured token
    // proves persistence + due scheduling without depending on the (separate) Review screen. The
    // active language id comes from GET /languages (the demo account has the one seeded language).
    const langsResponse = await request.get(`${API_BASE}/languages`, {
      headers: { Authorization: authHeader },
    });
    expect(langsResponse.ok()).toBeTruthy();
    const languages = (await langsResponse.json()) as { id: number }[];
    const languageId = languages[0].id;

    const due = await request.get(
      `${API_BASE}/review/due?language_id=${languageId}`,
      { headers: { Authorization: authHeader } },
    );
    expect(due.ok()).toBeTruthy();
    const body = (await due.json()) as {
      new: { front: string }[];
      due: { front: string }[];
    };
    const fronts = [...body.new, ...body.due].map((card) => card.front);
    expect(fronts.some((front) => front.includes(wordA))).toBe(true);
    expect(fronts.some((front) => front.includes(wordB))).toBe(false);
  });

  test('renders the shared daily-limit panel for a stubbed quota 429, preserving words', async ({
    page,
  }) => {
    await login(page);
    await gotoGenerate(page);

    // Stub the API's generate endpoint at the browser boundary (the server LLM seam is never hit).
    await page.route('**/generate', async (route) => {
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

    await page.getByLabel('Words', { exact: true }).fill('casa\nperro');
    await page.getByRole('button', { name: 'Generate' }).click();

    // 4.5.4 — the dedicated daily-limit panel (not a generic error), and the words are preserved.
    await expect(page.getByTestId('daily-limit-panel')).toBeVisible();
    await expect(page.getByText('Daily limit reached')).toBeVisible();
    await expect(page.getByLabel('Words', { exact: true })).toHaveValue(
      'casa\nperro',
    );
  });
});
