import { defineConfig, devices } from '@playwright/test';

const PORT = 4173;
// When an external base URL is provided (e.g. the CI E2E job serves the pre-built bundle from
// the `build` artifact and points us at it), use it and skip Playwright's own webServer.
// Otherwise default to a local preview that Playwright builds + serves itself.
const EXTERNAL_BASE_URL = process.env.PLAYWRIGHT_TEST_BASE_URL;
const BASE_URL = EXTERNAL_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Serve the production build for the smoke test. When PLAYWRIGHT_TEST_BASE_URL is set the
  // bundle is already being served externally, so we don't start a server here. Otherwise
  // `vite` is invoked via the locally-installed binary (resolved through the package runner)
  // so it does not depend on a global pnpm being on PATH.
  webServer: EXTERNAL_BASE_URL
    ? undefined
    : {
        command: `npx vite build && npx vite preview --port ${PORT} --strictPort`,
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
