import { expect, test } from '@playwright/test';

test('home loads', async ({ page }) => {
  const res = await page.goto('/');
  expect(res?.ok()).toBeTruthy();
  await expect(page.locator('#main-content')).toBeVisible();
});

test('case page renders', async ({ page }) => {
  const res = await page.goto('/cases/kariba-redd');
  expect(res?.status()).toBeLessThan(500);
  await expect(page.locator('body')).not.toBeEmpty();
});

test('no horizontal overflow at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ['/', '/cases/kariba-redd']) {
    await page.goto(path);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
});

test('demo-mode banner appears only with the explicit demo notice', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const banner = page.getByText('DEMO MODE — NO ANALYSIS WAS EXECUTED');
  // Banner is shown only when the API is unreachable AND demo mode is enabled;
  // when shown it must carry the "no project has been analysed" disclaimer.
  if (await banner.count()) {
    await expect(page.getByText(/No project has been analysed/)).toBeVisible();
  } else {
    await expect(banner).toHaveCount(0);
  }
});
