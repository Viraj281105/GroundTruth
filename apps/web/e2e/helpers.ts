import { expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { inflateRawSync } from 'node:zlib';
import { credentialsFor, REPO_ROOT, type Persona } from './seed';

export const WEB = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
export const API = process.env.E2E_API_URL ?? 'http://localhost:8000';
export const SCREENS_DIR = process.env.E2E_SCREENSHOTS_DIR ?? path.join(REPO_ROOT, 'docs', 'product', 'screens');

export const ORG: Record<Persona, string> = {
  ngo: 'demo-ngo',
  funder: 'demo-funder',
  auditor: 'demo-auditor',
  government: 'demo-government',
  operator: 'reference',
};

/** Kariba's real Level-2 values need the git-ignored caches; without them the value assertions skip. */
export const HAS_KARIBA_CACHES =
  existsSync(path.join(REPO_ROOT, 'data', 'processed', 'stac_cache')) &&
  existsSync(path.join(REPO_ROOT, 'data', 'processed', 'climate_cache'));

/** Keep the first-run tour from covering the page under test. */
export async function skipTour(page: Page): Promise<void> {
  await page.addInitScript(() => window.localStorage.setItem('gt-tour-seen', '1'));
}

/** Sign in through the real login form. */
export async function signInViaForm(page: Page, persona: Persona, next?: string): Promise<void> {
  const { email, password } = credentialsFor(persona);
  await page.goto(next ? `/login?next=${encodeURIComponent(next)}` : '/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** Sign in through the API (cookie lands in the browser context). Used where the login form is not under test. */
export async function signInViaApi(context: BrowserContext, persona: Persona): Promise<void> {
  const { email, password } = credentialsFor(persona);
  const res = await context.request.post(`${API}/auth/login`, {
    data: { email, password },
    headers: { Origin: WEB },
  });
  expect(res.status(), 'API sign-in').toBe(200);
}

export async function openDashboard(page: Page, persona: Persona): Promise<void> {
  await page.goto(`/app/${ORG[persona]}/dashboard`);
  await expect(page.locator('[data-persona-question]')).toBeVisible();
}

export async function screenshot(page: Page, info: TestInfo, name: string, opts: { phone?: boolean } = {}): Promise<void> {
  const phone = info.project.name === 'phone';
  if (phone && !opts.phone) return;
  mkdirSync(SCREENS_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SCREENS_DIR, `${name}${phone ? '-phone' : ''}.png`), fullPage: true });
}

/** Reads a stored/deflated entry out of a ZIP buffer through its central directory. Throws if not a valid zip. */
export function zipEntry(buf: Buffer, wanted: string): Buffer | null {
  const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (eocd < 0) throw new Error('not a zip: no end-of-central-directory record');
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('corrupt central directory');
    const method = buf.readUInt16LE(p + 10);
    const size = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const name = buf.subarray(p + 46, p + 46 + nameLen).toString('utf8');
    if (name === wanted) {
      const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
      const data = buf.subarray(start, start + size);
      return method === 0 ? data : inflateRawSync(data);
    }
    p += 46 + nameLen + extraLen + commentLen;
  }
  return null;
}
