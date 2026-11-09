import { defineConfig, devices } from '@playwright/test';

/**
 * Live demo-integrity run (e2e/task4a.spec.ts) against a stack you started yourself.
 *   E2E_BASE_URL   web app, default http://localhost:3000
 *   E2E_CHANNEL    installed browser to use instead of a downloaded one: chrome | msedge
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /task4a\.spec\.ts/,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
    acceptDownloads: true,
    ...devices['Desktop Chrome'],
    ...(process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {}),
  },
});

