import { defineConfig } from 'vitest/config';

// Playwright specs in e2e/ run under `npm run test:e2e`, not the unit runner.
export default defineConfig({
  test: { exclude: ['e2e/**', 'node_modules/**', '.next/**'] },
});
