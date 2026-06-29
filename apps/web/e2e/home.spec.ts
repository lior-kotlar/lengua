import { expect, test } from "@playwright/test";

test("home page renders the placeholder", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Lengua" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Get started" })).toBeVisible();
});
