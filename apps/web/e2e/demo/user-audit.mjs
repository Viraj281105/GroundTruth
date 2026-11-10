// User-perspective crawl of a running GroundTruth stack. It signs in through the login form,
// then reaches every page by CLICKING links (sidebar, project list, project tabs), the way a
// person does, and records what a person would call broken: error pages, failed requests,
// console errors. It changes nothing on the server.
//
//   node e2e/demo/user-audit.mjs <persona> [maxProjects]
//
//   AUDIT_BASE_URL        web app (default http://localhost:3100, the isolated demo stack)
//   AUDIT_PASSWORDS_FILE  TSV of email<TAB>password written by the demo seed
//   AUDIT_OUT             output directory for the JSON report and screenshots
//   AUDIT_CHANNEL         installed browser: chrome (default) | msedge
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const persona = process.argv[2] ?? 'ngo';
const maxProjects = Number(process.argv[3] ?? 2);
const base = process.env.AUDIT_BASE_URL ?? 'http://localhost:3100';
const outDir = path.resolve(process.env.AUDIT_OUT ?? 'audit-out', persona);
fs.mkdirSync(outDir, { recursive: true });

const creds = Object.fromEntries(
  fs
    .readFileSync(process.env.AUDIT_PASSWORDS_FILE, 'utf8')
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => line.split('\t')),
);
const email = `${persona}@demo.groundtruth.local`;
if (!creds[email]) throw new Error(`no credentials for ${email}`);

const browser = await chromium.launch({ channel: process.env.AUDIT_CHANNEL ?? 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

let events = [];
page.on('console', (m) => {
  if (m.type() === 'error') events.push({ kind: 'console', text: m.text().slice(0, 400) });
});
page.on('pageerror', (e) => events.push({ kind: 'pageerror', text: String(e).slice(0, 400) }));
page.on('response', (r) => {
  if (r.status() >= 400) {
    events.push({ kind: 'http', status: r.status(), method: r.request().method(), url: r.url() });
  }
});
page.on('requestfailed', (r) => {
  const failure = r.failure()?.errorText ?? '';
  if (!/ERR_ABORTED/.test(failure)) events.push({ kind: 'requestfailed', url: r.url(), failure });
});

const visits = [];
let shot = 0;

async function settle() {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(400);
}

async function record(action) {
  await settle();
  const body = (await page.locator('body').innerText().catch(() => '')) ?? '';
  const flags = [];
  if (/\b404\b|could not be found|not found/i.test(body)) flags.push('not-found-text');
  if (/application error|something went wrong|unexpected error|\b500\b/i.test(body)) flags.push('error-text');
  if (/\bundefined\b|\bNaN\b|\[object Object\]/.test(body)) flags.push('raw-value-leak');
  const h1 = await page.locator('h1').first().innerText({ timeout: 1000 }).catch(() => null);
  const file = `${String(++shot).padStart(2, '0')}-${action.replace(/[^a-z0-9]+/gi, '-').slice(0, 60)}.png`;
  await page.screenshot({ path: path.join(outDir, file), fullPage: true }).catch(() => {});
  visits.push({ action, url: page.url().replace(base, ''), h1, flags, events, screenshot: file, textHead: body.slice(0, 300) });
  events = [];
}

// --- sign in through the form ---------------------------------------------------------------
await page.goto(`${base}/login`);
await page.getByLabel('Email').fill(email);
await page.getByLabel('Password', { exact: true }).fill(creds[email]);
await page.getByRole('button', { name: 'Sign in' }).click();
await page.waitForURL(/\/app\//, { timeout: 20000 }).catch(() => {});
await record('sign in');

// A first sign-in opens the welcome tour. Step through it as a new user would, keeping its text.
const tour = [];
for (let step = 0; step < 8; step++) {
  const dialog = page.getByRole('dialog').first();
  if (!(await dialog.isVisible().catch(() => false))) break;
  tour.push((await dialog.innerText()).replace(/\s+/g, ' '));
  const next = dialog.getByRole('button', { name: /^(Next|Done|Finish|Get started|Start)/ }).first();
  if (await next.isVisible().catch(() => false)) await next.click();
  else await dialog.getByRole('button').first().click();
  await page.waitForTimeout(300);
}
await record('after welcome tour');

const landing = page.url();
const org = (landing.match(/\/app\/([^/]+)/) ?? [])[1];

/** Unique same-app hrefs currently on the page, in document order. */
async function hrefs(selector) {
  const all = await page.locator(selector).evaluateAll((els) => els.map((a) => a.getAttribute('href')));
  return [...new Set(all.filter((h) => h && h.startsWith('/app/')))];
}

async function clickHref(href, label) {
  const link = page.locator(`a[href="${href}"]`).first();
  try {
    await link.scrollIntoViewIfNeeded({ timeout: 3000 });
    await link.click({ timeout: 5000 });
  } catch (error) {
    events.push({ kind: 'click-failed', text: `${href}: ${String(error).slice(0, 200)}` });
    await page.goto(base + href);
  }
  await record(label);
}

// --- every sidebar destination ---------------------------------------------------------------
const navLinks = await hrefs('nav a, aside a');
for (const href of navLinks) {
  await clickHref(href, `nav ${href.replace(`/app/${org}/`, '')}`);
}

// --- projects: open from the list, then every tab ---------------------------------------------
await page.goto(`${base}/app/${org}/projects`);
await settle();
const projectLinks = (await hrefs('main a')).filter((h) => /\/projects\/[^/]+(\/overview)?$/.test(h) && !h.endsWith('/new'));
for (const href of projectLinks.slice(0, maxProjects)) {
  await page.goto(`${base}/app/${org}/projects`);
  await settle();
  await clickHref(href, `project ${href.split('/projects/')[1]}`);
  const projectBase = page.url().replace(base, '').replace(/\/[^/]+$/, '');
  const tabs = (await hrefs('main a, header a')).filter((h) => h.startsWith(projectBase + '/'));
  for (const tab of tabs) {
    await clickHref(tab, `tab ${tab.replace(`/app/${org}/projects/`, '')}`);
  }
}

// --- every other in-app link seen on the main pages (catches dead links) ----------------------
const seen = new Set(visits.map((v) => v.url));
const extra = new Set();
for (const start of [`/app/${org}/dashboard`, `/app/${org}/reports`, `/app/${org}/assessments`, `/app/${org}/portfolio`]) {
  await page.goto(base + start);
  await settle();
  for (const h of await hrefs('main a')) if (!seen.has(h)) extra.add(h);
}
events = [];
for (const href of [...extra].slice(0, 25)) {
  const response = await page.goto(base + href);
  events.push({ kind: 'direct', status: response?.status() });
  await record(`link ${href.replace(`/app/${org}/`, '')}`);
}

fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify({ persona, org, tour, projectLinks, visits }, null, 1));
console.log('tour:', tour.length ? tour.join('\n      ') : '(none shown)');
for (const v of visits) {
  const bad = v.events.filter((e) => e.kind !== 'direct');
  console.log(`${v.flags.length || bad.length ? '!!' : 'ok'} ${v.action} -> ${v.url} [${v.h1 ?? '-'}] ${v.flags.join(',')}`);
  for (const e of bad) console.log(`     ${e.kind} ${e.status ?? ''} ${e.method ?? ''} ${e.url ?? e.text ?? ''}`);
}
await browser.close();
