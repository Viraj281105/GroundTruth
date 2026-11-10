// Brings a freshly seeded demo stack to the state the walkthrough and the recording start from,
// by doing what the NGO user does in the browser: create the project, upload the design note,
// request real Sentinel-2 observations and wait for the worker, add the extracted statements as
// claims, and share the project with the funder (view) and the auditor (audit).
//
// Nothing is written to the database directly, and no dossier is created (the recording does
// that live). Safe to re-run: steps that are already done are skipped.
//
//   node e2e/demo/prepare-demo.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { open, signIn, settle, printEvents, base } from './lib.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const NAME = 'Sahyadri Foothills Restoration (demonstration)';
const SLUG = 'sahyadri-foothills-restoration-demonstration';
const { browser, page, events, shot } = await open({ name: 'prepare-demo' });
const main = page.locator('main');
const nav = page.getByRole('navigation', { name: 'Main', exact: true });
const tab = async (name) => {
  await main.getByRole('link', { name, exact: true }).first().click();
  await settle(page, 1000);
};
const step = (text) => console.log(`[prepare] ${text}`);

const org = await signIn(page, 'ngo');

// 1. project --------------------------------------------------------------------------------
await nav.getByRole('link', { name: 'Projects', exact: true }).click();
await settle(page);
if (await main.getByRole('link', { name: /Sahyadri Foothills/ }).count()) {
  step('project exists');
} else {
  await nav.getByRole('link', { name: 'New project' }).click();
  await settle(page);
  await page.getByLabel('Project name').fill(NAME);
  await page.getByLabel('Country').fill('India');
  await page.getByLabel('Ecosystem').fill('dry deciduous hill forest');
  await page.getByLabel('Intervention').fill('restoration');
  await page.getByLabel('Treatment start year').fill('2021');
  await page.getByLabel('Boundary file').setInputFiles(path.join(here, 'fixtures', 'demo-boundary-pune.geojson'));
  await page.getByRole('button', { name: 'Create project' }).click();
  await page.waitForURL(new RegExp(`/projects/${SLUG}`), { timeout: 30000 });
  step('project created');
}
await page.goto(`${base}/app/${org}/projects/${SLUG}/evidence`);
await settle(page, 1000);

// 2. document -------------------------------------------------------------------------------
if (await main.getByText('demo-project-design-note.md').count()) {
  step('document exists');
} else {
  await page.locator('input[type=file]').first().setInputFiles(path.join(here, 'fixtures', 'demo-project-design-note.md'));
  await page.getByRole('button', { name: 'Upload document' }).click();
  await main.getByText('possible claims found').waitFor({ timeout: 30000 });
  step('document uploaded');
}

// 3. satellite observations -------------------------------------------------------------------
await tab('Earth Observation');
const finished = main.getByText('Finished', { exact: true }).first();
if (await finished.count()) {
  step('observations already stored');
} else {
  await main.getByText('Choose my own dates').click();
  await main.getByLabel('Season starts (MM-DD)').fill('01-15');
  await main.getByLabel('Season ends (MM-DD)').fill('03-15');
  for (const name of [/^EVI/, /^NDMI/, /^NBR/]) await main.getByRole('checkbox', { name }).check();
  await main.getByText('Advanced options').click();
  await main.getByLabel(/Cloud limit/).fill('20');
  await main.getByLabel(/Scenes per year/).fill('2');
  await main.getByRole('button', { name: 'Request satellite data' }).click();
  step('satellite data requested; waiting for the worker (real download, usually under two minutes)');
  const started = Date.now();
  await finished.waitFor({ timeout: 10 * 60 * 1000 });
  step(`observations stored after ${Math.round((Date.now() - started) / 1000)} s`);
  await shot('observations', true);
}

// 4. claims -----------------------------------------------------------------------------------
await tab('Evidence');
await main.getByRole('button', { name: /extracted statements/i }).first().click();
await settle(page, 1200);
let promoted = 0;
while (await main.getByRole('button', { name: 'Review and add as claim' }).count()) {
  await main.getByRole('button', { name: 'Review and add as claim' }).first().click();
  await page.getByRole('button', { name: 'Add as claim', exact: true }).click();
  await settle(page, 1000);
  promoted += 1;
  if (promoted > 10) throw new Error('claim promotion did not converge');
}
step(`claims added now: ${promoted}`);
// Close the statements dialog, as a person would, before using the sidebar again.
const close = page.getByRole('dialog').getByRole('button', { name: /close|×/i }).first();
if (await close.isVisible().catch(() => false)) await close.click();
else await page.keyboard.press('Escape');
await page.waitForTimeout(400);

// 5. sharing ----------------------------------------------------------------------------------
await nav.getByRole('link', { name: 'Sharing', exact: true }).click();
await settle(page, 1000);
for (const [slug, level] of [['demo-funder', 'view'], ['demo-auditor', 'audit']]) {
  if (await main.getByText(`(${slug})`).count()) continue;
  await main.getByLabel('Organization slug').fill(slug);
  await main.getByLabel('Level').selectOption(level);
  await main.getByRole('button', { name: 'Grant access' }).click();
  await main.getByText(`(${slug})`).waitFor({ timeout: 15000 });
  step(`shared with ${slug} (${level})`);
}
await shot('sharing', true);
printEvents(events);
await browser.close();
step('ready');
