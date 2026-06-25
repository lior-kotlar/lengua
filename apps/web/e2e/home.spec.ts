import { expect, test } from '@playwright/test';

test('home page renders the placeholder and sample component', async ({
  page,
}) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: /lengua/i })).toBeVisible();

  const cta = page.getByTestId('cta-button');
  await expect(cta).toBeVisible();
  await expect(cta).toHaveText('Get started');
});
