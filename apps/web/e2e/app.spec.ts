import { expect, test } from '@playwright/test';

const ROUTES = [
  '/',
  '/login',
  '/register',
  '/cases',
  '/cases/kariba-redd',
  '/cases/kariba-redd/evidence',
  '/cases/kariba-redd/robustness',
  '/cases/kariba-redd/method',
  '/cases/kariba-redd/report',
  '/cases/kariba-redd/run',
  '/compare?a=kariba-redd&b=mikoko-pamoja',
  '/claims',
  '/method',
  '/status',
];

test.beforeEach(async ({ page }) => {
  // Skip the first-run tour so it never covers the page under test.
  await page.addInitScript(() => window.localStorage.setItem('gt-tour-seen', '1'));
});

for (const path of ROUTES) {
  test(`${path} loads with the simulated-data chip`, async ({ page }) => {
    const res = await page.goto(path);
    expect(res?.status()).toBeLessThan(500);
    await expect(page.locator('#main-content')).toBeVisible();
    // R7: the marker is on every page and cannot be dismissed.
    await expect(page.getByText('Simulated data').first()).toBeVisible();
  });
}

test('no horizontal overflow on any route at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ROUTES) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
});

test('theme toggle switches between light and dark and is remembered', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  const html = page.locator('html');
  await expect(html).toHaveAttribute('data-theme', 'light');
  await page.getByRole('button', { name: /Theme:/ }).click(); // system -> light
  await page.getByRole('button', { name: /Theme:/ }).click(); // light -> dark
  await expect(html).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(html).toHaveAttribute('data-theme', 'dark');
});

test('command palette resolves a natural-language compare', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Control+k');
  await page.getByRole('combobox', { name: 'Command' }).fill('compare kariba and mikoko');
  await expect(page.getByRole('option', { name: /Compare kariba and mikoko/i })).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/compare\?a=kariba-redd&b=mikoko-pamoja/);
});

test('detail level (lens) is remembered and can be set from the URL', async ({ page }) => {
  await page.goto('/?lens=auditor');
  await expect(page.getByRole('radio', { name: 'Auditor' })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('radio', { name: 'Story' }).click();
  await page.goto('/cases');
  await expect(page.getByRole('radio', { name: 'Story' })).toHaveAttribute('aria-checked', 'true');
});

test('keyboard: g then c goes to Cases; ? opens the shortcut help', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('g');
  await page.keyboard.press('c');
  await expect(page).toHaveURL(/\/cases$/);
  await page.keyboard.press('Shift+Slash');
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible();
});

test('an unknown case shows a way back, not a blank page', async ({ page }) => {
  await page.goto('/cases/not-a-real-case');
  await expect(page.getByRole('link', { name: /cases/i }).first()).toBeVisible();
});
