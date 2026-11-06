import { expect, test } from '@playwright/test';

test('home visual regression', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('home.png', { fullPage: true });
});

test('case page visual regression', async ({ page }) => {
  await page.goto('/cases/kariba-redd');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('case-kariba.png', { fullPage: true });
});
