import { expect, test } from './fixtures';

/**
 * Mobile shell smoke at 390×844 (redesign PR2) — runs against the seeded demo account on the
 * ephemeral stack, like the other authed flows (gated on E2E_STACK=1).
 *
 * Verifies the phone-viewport navigation story the desktop specs can't: the fixed bottom tab bar
 * is the visible list inside the single Primary nav landmark (the sidebar list is display-hidden,
 * so Playwright's role engine keeps `nav → link` queries unambiguous), the More sheet reaches the
 * remaining destinations, and toasts render ABOVE the tab bar (the viewport is offset by
 * 49px + safe-area so "Settings saved"/"Cards saved" are never covered).
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

test.use({ viewport: { width: 390, height: 844 } });

test.describe('mobile shell (390px, ephemeral stack)', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('tab bar navigates, More sheet reaches Settings, toast renders above the bar', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(DEMO_EMAIL);
    await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(
      page.getByRole('heading', { name: 'Dashboard' }),
    ).toBeVisible();

    // At 390px the tab bar is the visible Primary-nav list; the sidebar list is hidden.
    const tabBar = page.getByTestId('nav-mobile');
    await expect(tabBar).toBeVisible();
    await expect(page.getByTestId('nav-desktop')).toBeHidden();

    // The role engine sees exactly one "Generate" link inside the landmark at this viewport.
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: 'Generate' })
      .click();
    await expect(page.getByRole('heading', { name: 'Generate' })).toBeVisible();

    // Settings lives behind the More sheet on phones.
    await tabBar.getByRole('button', { name: 'More' }).click();
    const sheet = page.getByRole('dialog', { name: 'More' });
    await expect(sheet).toBeVisible();
    await sheet.getByRole('link', { name: 'Settings' }).click();
    await expect(sheet).toBeHidden();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

    // Fire a real toast and assert it stacks above the tab bar, never beneath it.
    await page.getByRole('button', { name: 'Save settings' }).click();
    await expect(page.getByText('Settings saved')).toBeVisible();
    const viewportBox = await page
      .locator('ol')
      .filter({ has: page.getByText('Settings saved') })
      .boundingBox();
    const barBox = await tabBar.boundingBox();
    expect(viewportBox).not.toBeNull();
    expect(barBox).not.toBeNull();
    expect(viewportBox!.y + viewportBox!.height).toBeLessThanOrEqual(
      barBox!.y + 1,
    );
  });
});
