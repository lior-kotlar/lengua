import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the LIVE-staging browser pass (NOT part of CI).
 *
 * Unlike the default `playwright.config.ts` (which builds + serves the bundle locally for the
 * deterministic FakeLLM e2e suite), this config drives a real browser against the deployed staging
 * site. It therefore:
 *   - has NO `webServer` — it never builds or serves anything; it hits the live origin;
 *   - reads its base URL from `PLAYWRIGHT_TEST_BASE_URL`, defaulting to the stable staging alias;
 *   - uses generous timeouts (Cloud Run cold starts + real Groq are slow) and one retry.
 *
 * The specs live in `./e2e-staging` (a directory the default config and CI never touch) and are run
 * only on demand via `pnpm test:e2e-staging` / `npm run test:e2e-staging`. They are deliberately
 * excluded from `ci.yml`, the default `playwright test`, vitest, and coverage so the gate never
 * exercises live staging.
 */
const BASE_URL =
  process.env.PLAYWRIGHT_TEST_BASE_URL ?? 'https://lengua-staging.vercel.app';

export default defineConfig({
  testDir: './e2e-staging',
  // Each spec logs in independently, so they can run in parallel against the live site.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Live staging is inherently a little flaky (cold starts, real network); one retry absorbs that.
  retries: 1,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  // Generous global per-test budget — a cold Cloud Run instance plus a real login can be slow.
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: BASE_URL,
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
