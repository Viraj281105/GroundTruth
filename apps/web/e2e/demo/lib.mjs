// Shared helpers for the user-perspective demo scripts (audit journeys and the video recording).
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

export const base = process.env.AUDIT_BASE_URL ?? 'http://localhost:3100';
export const apiBase = process.env.AUDIT_API_URL ?? 'http://localhost:8100';
export const outRoot = path.resolve(process.env.AUDIT_OUT ?? 'audit-out');

export function credentials() {
  const file = process.env.AUDIT_PASSWORDS_FILE;
  if (!file) throw new Error('AUDIT_PASSWORDS_FILE is not set');
  return Object.fromEntries(
    fs
      .readFileSync(file, 'utf8')
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => line.split('\t')),
  );
}

/** Launch a browser page that records console errors, page errors and failed requests. */
export async function open({ name, viewport = { width: 1440, height: 900 }, contextOptions = {} }) {
  const outDir = path.join(outRoot, name);
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.AUDIT_CHANNEL ?? 'chrome' });
  const context = await browser.newContext({ viewport, acceptDownloads: true, ...contextOptions });
  const page = await context.newPage();
  const events = [];
  page.on('console', (m) => {
    if (m.type() === 'error') events.push({ kind: 'console', text: m.text().slice(0, 400), at: page.url() });
  });
  page.on('pageerror', (e) => events.push({ kind: 'pageerror', text: String(e).slice(0, 400), at: page.url() }));
  page.on('response', (r) => {
    if (r.status() >= 400) {
      events.push({ kind: 'http', status: r.status(), method: r.request().method(), url: r.url(), at: page.url() });
    }
  });
  let n = 0;
  const shot = async (label, fullPage = false) => {
    const file = path.join(outDir, `${String(++n).padStart(2, '0')}-${label.replace(/[^a-z0-9]+/gi, '-')}.png`);
    await page.screenshot({ path: file, fullPage });
    return file;
  };
  return { browser, context, page, events, outDir, shot };
}

export async function settle(page, extra = 400) {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(extra);
}

/** Sign in through the login form, as a person does, and close the first-visit tour. */
export async function signIn(page, persona, { skipTour = true } = {}) {
  const email = persona.includes('@') ? persona : `${persona}@demo.groundtruth.local`;
  const password = credentials()[email];
  if (!password) throw new Error(`no credentials for ${email}`);
  await page.goto(`${base}/login`);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(/\/app\//, { timeout: 20000 });
  await settle(page);
  if (skipTour) await closeTour(page);
  return (page.url().match(/\/app\/([^/]+)/) ?? [])[1];
}

export async function closeTour(page) {
  const skip = page.getByRole('button', { name: 'Skip', exact: true });
  if (await skip.isVisible().catch(() => false)) {
    await skip.click();
    await page.waitForTimeout(300);
  }
}

export function printEvents(events) {
  if (!events.length) return console.log('events: none');
  for (const e of events) console.log(`event ${e.kind} ${e.status ?? ''} ${e.method ?? ''} ${e.url ?? e.text} @ ${e.at?.replace(base, '')}`);
}

export async function mainText(page, max = 3000) {
  const text = await page.locator('main').innerText().catch(() => '');
  return text.replace(/\n{2,}/g, '\n').slice(0, max);
}
