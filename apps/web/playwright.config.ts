import { defineConfig, devices } from '@playwright/test';

/**
 * E2E_CHANNEL   installed browser instead of the bundled chromium: chrome | msedge (unset = bundled chromium)
 * E2E_BASE_URL  web origin the tests drive (default http://localhost:3000); e2e/stack.ts serves on it.
 * See e2e/README.md.
 */
const channel = process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {};

export default defineConfig({
  testDir: './e2e',
  // The pre-2.0 specs (app, task4a, visual) drive routes that now redirect; they are not part of this run.
  // csp: every page renders under the Content-Security-Policy (#51).
  // runs: a run from the UI to the rendered result, refusal, cancel and failure included (#49).
  testMatch: /(personas|a11y|csp|runs)\.spec\.ts/,
  globalSetup: './e2e/stack.ts',
  fullyParallel: true,
  // One API process serves every worker and the Kariba assessment is computed per request: keep the load modest.
  workers: 3,
  timeout: 90_000,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
    acceptDownloads: true,
    trace: 'on-first-retry',
  },
  expect: { timeout: 20_000, toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], ...channel } },
    {
      name: 'phone',
      use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 }, hasTouch: true, ...channel },
    },
  ],
});
