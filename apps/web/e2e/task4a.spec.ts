import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';

/**
 * Task 4A: register, case creation with the session cookie, PDF/CSV downloads that are
 * real files, and a fresh run that is never replaced by the precomputed fixture.
 * Needs the API, a worker and the web app running (see TASK_4A_REMEDIATION_REPORT.md).
 * The account is created per run with a random password; nothing is seeded.
 */
test.describe.configure({ mode: 'serial' });

let context: BrowserContext;
let page: Page;

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ acceptDownloads: true });
  page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem('gt-tour-seen', '1'));
});

test.afterAll(async () => {
  await context?.close();
});

const email = `e2e-${randomBytes(4).toString('hex')}@example.test`;
const password = `Aa1!${randomBytes(12).toString('base64url')}`;

test('register, create a case with the session cookie', async () => {
  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('textbox', { name: 'Confirm password' }).fill(password);
  await page.getByRole('button', { name: /create account|register|sign up/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/register'));

  await page.goto('/cases/new');
  const name = `E2E ${randomBytes(3).toString('hex')}`;
  await page.getByLabel('Project Name').fill(name);
  const created = page.waitForResponse((r) => r.url().endsWith('/cases') && r.request().method() === 'POST');
  await page.getByRole('button', { name: /Create & Verify Project/ }).click();
  const res = await created;
  expect(res.status(), 'POST /cases must carry the session cookie').toBeLessThan(300);
  await page.waitForURL(/\/cases\/e2e-/);
});

test('session persists across a reload', async () => {
  await page.goto('/account');
  await expect(page.getByText(email)).toBeVisible();
});

test('report downloads are real PDF and CSV files', async () => {
  await page.goto('/cases/kariba-redd/report');
  const pdfDl = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  const pdf = await pdfDl;
  const pdfPath = await pdf.path();
  const pdfBytes = readFileSync(pdfPath);
  expect(pdf.suggestedFilename()).toBe('kariba-redd-report.pdf');
  expect(pdfBytes.subarray(0, 5).toString('latin1')).toBe('%PDF-');
  expect(pdfBytes.subarray(-1024).toString('latin1')).toContain('%%EOF');

  const csvDl = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download CSV' }).click();
  const csv = await csvDl;
  const text = readFileSync((await csv.path())!, 'utf8');
  expect(csv.suggestedFilename()).toBe('kariba-redd-evidence.csv');
  expect(text).toContain('data_origin: SYNTHETIC_SIMULATION');
  expect(text).toContain('effect.point_estimate');
});

test('a failed download is reported, not swallowed', async () => {
  await page.route('**/cases/kariba-redd/export/pdf', (route) => route.fulfill({ status: 401, body: '{"detail":"Not authenticated"}' }));
  await page.goto('/cases/kariba-redd/report');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  await expect(page.getByRole('alert').filter({ hasText: /not signed in/i })).toBeVisible();
  await page.unroute('**/cases/kariba-redd/export/pdf');
});

test('precomputed evidence is labelled a synthetic benchmark', async () => {
  await page.goto('/cases/kariba-redd/evidence');
  await expect(page.getByText('Synthetic benchmark - precomputed')).toBeVisible();
  await expect(page.getByText('Carbon impact is not calibrated')).toBeVisible();
});

test('a fresh run is shown as itself, never as the older fixture', async () => {
  await page.goto('/cases/kariba-redd/run');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByText('Analysis complete')).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/not live satellite ingestion/i).first()).toBeVisible();
  await page.getByRole('link', { name: 'Open the evidence' }).click();
  await page.waitForURL(/evidence\?run=/);
  await expect(page.getByText('Fresh run on the synthetic benchmark engine')).toBeVisible();
  await expect(page.getByText('Synthetic benchmark - precomputed')).toHaveCount(0);
  await expect(page.locator('[data-viz-unavailable="true"]')).toBeVisible();
});
