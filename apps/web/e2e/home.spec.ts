import { expect, test } from '@playwright/test';

// The app shell renders without API/Supabase env (Supabase is initialized lazily, only when an
// auth-touching screen needs it), so this smoke runs against the env-less preview bundle. Auth
// gating + a full-loop E2E land in group 4.3 on the ephemeral stack.
test('home renders the app shell at /', async ({ page }) => {
  await page.goto('/');

  // Brand in the header.
  await expect(page.getByRole('link', { name: 'Lengua' })).toBeVisible();

  // The authenticated Dashboard screen mounts inside the shell.
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  // Primary navigation is present.
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole('link', { name: 'Review' })).toBeVisible();
});
