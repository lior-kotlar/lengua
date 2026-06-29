import { defineConfig, devices } from "@playwright/test";

// In CI we exercise the production build (`pnpm preview` serving `dist`); locally we use
// the dev server for fast feedback. The CI job runs `pnpm build` before the suite.
const isCI = !!process.env.CI;
const PORT = isCI ? 4173 : 5173;
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: isCI
      ? `pnpm preview --port ${PORT} --strictPort`
      : `pnpm dev --port ${PORT} --strictPort`,
    url: baseURL,
    reuseExistingServer: !isCI,
    timeout: 120_000,
  },
});
