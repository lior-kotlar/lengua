import { expect, test, type Page } from './fixtures';

/**
 * Language management & CEFR level E2E (group 4.4) — runs against the seeded demo account on the
 * ephemeral stack (Supabase + the API container with LLM_PROVIDER=fake). None of these flows touch
 * the LLM seam, so the zero-real-LLM guarantee is preserved (the CI job asserts the FakeLLM counter
 * separately). Gated on E2E_STACK=1 like the auth flows; the seeded demo has one language (Spanish)
 * with no recorded proficiency, so it reads as band A1.
 *
 * The test adds a throwaway language (unique per run), exercises the picker / CEFR panel / override,
 * then removes it — leaving the demo account as it found it.
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

test.describe('language management & CEFR level (ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('picker, add, scope, override and remove a language', async ({
    page,
  }) => {
    const throwaway = `ZZ E2E ${Date.now()}`;
    const picker = page.getByLabel('Active language');
    const level = page.getByRole('region', { name: 'Proficiency level' });
    const band = level.getByTestId('cefr-band');

    await login(page);

    // 4.4.1 / 4.4.4 — the picker lists the seeded language and the CEFR panel shows its band (A1).
    await expect(picker).toBeVisible();
    await expect(picker.getByRole('option', { name: 'Spanish' })).toHaveCount(
      1,
    );
    await expect(band).toHaveText('A1');

    // 4.4.2 — add a language with a non-default starting band (B1 → create + PUT proficiency).
    // A timestamp-unique throwaway name is not on the curated list, so this drives the picker's
    // custom (experimental) path (issue #95): search → "Add … as a custom language…" → the
    // free-form Name/Code/level fields.
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Languages' })
      .click();
    // `exact` so this is the picker's "Language" combobox, not the header "Active language" one
    // (Playwright's accessible-name match is a substring by default).
    await page
      .getByRole('combobox', { name: 'Language', exact: true })
      .fill(throwaway);
    await page.getByRole('option', { name: /as a custom language/ }).click();
    await page.getByLabel('Name').fill(throwaway);
    await page.getByLabel('Code (optional)').fill('eo');
    await page.getByLabel('Starting level').selectOption('B1');
    await page.getByRole('button', { name: 'Add language' }).click();

    // It appears in the management list (the remove control is the unambiguous per-row anchor).
    const removeButton = page.getByRole('button', {
      name: `Remove ${throwaway}`,
    });
    await expect(removeButton).toBeVisible();
    // ...and in the header picker (it was auto-selected as active on create).
    await expect(picker.getByRole('option', { name: throwaway })).toHaveCount(
      1,
    );

    // 4.4.1 / 4.4.4 — switching the picker re-scopes the CEFR panel to each language's own level.
    await expect(band).toHaveText('B1'); // the new language, now active, at its B1 start
    await picker.selectOption({ label: 'Spanish' });
    await expect(band).toHaveText('A1'); // back to the demo language's A1
    await picker.selectOption({ label: throwaway });
    await expect(band).toHaveText('B1');

    // 4.4.5 — manual override updates the level for the active language.
    await page.getByLabel('Override level').selectOption('C1');
    await expect(band).toHaveText('C1');

    // 4.4.3 — remove the throwaway via the confirm dialog; it leaves the list and the picker.
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Languages' })
      .click();
    await page.getByRole('button', { name: `Remove ${throwaway}` }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Remove' }).click();

    await expect(
      page.getByRole('button', { name: `Remove ${throwaway}` }),
    ).toHaveCount(0);
    await expect(picker.getByRole('option', { name: throwaway })).toHaveCount(
      0,
    );
  });

  test('curated pick → submit adds the language, then removes it', async ({
    page,
  }) => {
    // The feature's PRIMARY new flow (issue #95): search the curated list, pick a real curated
    // language (NOT the custom fallback the other spec drives), choose a starting band, and submit.
    // The demo seed owns Spanish only, so "French" is guaranteed absent at the start.
    const picker = page.getByLabel('Active language');
    const level = page.getByRole('region', { name: 'Proficiency level' });
    const band = level.getByTestId('cefr-band');

    await login(page);

    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Languages' })
      .click();

    // Curated picker: type "French", then click the CURATED "French" option (its accessible name
    // starts with "French …"), not the custom row (`Add "French" as a custom language…`).
    await page
      .getByRole('combobox', { name: 'Language', exact: true })
      .fill('French');
    await page.getByRole('option', { name: /^French/ }).click();

    // The curated step shows a read-only chip (no Name/Code inputs) — the primary difference from
    // the custom path. Pick a non-default band so the create + proficiency PUT both run.
    await expect(page.getByText('Français')).toBeVisible();
    await expect(page.getByLabel('Name')).toHaveCount(0);
    await page.getByLabel('Starting level').selectOption('B1');
    await page.getByRole('button', { name: 'Add language' }).click();

    // It lands in the management list and the header picker (auto-selected active on create), at B1.
    const removeButton = page.getByRole('button', { name: 'Remove French' });
    await expect(removeButton).toBeVisible();
    await expect(picker.getByRole('option', { name: 'French' })).toHaveCount(1);
    await expect(band).toHaveText('B1');

    // Clean up: remove French so the demo account is left as it was found.
    await removeButton.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Remove' }).click();

    await expect(
      page.getByRole('button', { name: 'Remove French' }),
    ).toHaveCount(0);
    await expect(picker.getByRole('option', { name: 'French' })).toHaveCount(0);
  });
});
