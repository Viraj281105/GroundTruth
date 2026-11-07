import { expect, test } from '@playwright/test';

/**
 * Visual regression across the main routes in both themes.
 * Baselines are not committed: generate them once with
 *   npx playwright test e2e/visual.spec.ts --update-snapshots
 * and review the images before committing them.
 */
const PAGES: Array<[string, string]> = [
  ['home', '/'],
  ['cases', '/cases'],
  ['case-overview', '/cases/kariba-redd'],
  ['case-evidence', '/cases/kariba-redd/evidence'],
  ['compare', '/compare?a=kariba-redd&b=mikoko-pamoja'],
  ['claims', '/claims'],
  ['method', '/method'],
];

for (const scheme of ['light', 'dark'] as const) {
  for (const [name, path] of PAGES) {
    test(`${name} (${scheme})`, async ({ page }) => {
      await page.addInitScript(() => window.localStorage.setItem('gt-tour-seen', '1'));
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveScreenshot(`${name}-${scheme}.png`, { fullPage: true, maxDiffPixelRatio: 0.02 });
    });
  }
}
