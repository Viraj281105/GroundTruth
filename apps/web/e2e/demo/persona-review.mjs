// Funder / auditor journey on the shared project: open it from the project list, read every
// tab, list the controls each role is offered, try the dossier, and confirm the server refuses
// what the role must not do. First argument: funder | auditor
import fs from 'node:fs';
import path from 'node:path';
import { open, signIn, settle, printEvents, mainText, base, apiBase } from './lib.mjs';

const persona = process.argv[2] ?? 'funder';
const { browser, page, context, events, shot, outDir } = await open({ name: `review-${persona}` });
const main = page.locator('main');
const afterTabs = (text) => text.split('\nActivity\n').slice(1).join('\nActivity\n');

const org = await signIn(page, persona);
await shot('dashboard', true);
console.log('=== DASHBOARD ===\n' + (await mainText(page, 2500)));
await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'Projects', exact: true }).click();
await settle(page);
console.log('=== PROJECTS ===\n' + (await mainText(page, 1500)));
await main.getByRole('link', { name: /Sahyadri Foothills/ }).first().click();
await settle(page, 1500);
const badges = await mainText(page, 400);
console.log('=== PROJECT HEADER ===\n' + badges);
const projectUrl = page.url();

for (const name of ['Overview', 'Earth Observation', 'Evidence', 'Verification', 'Reports', 'Activity']) {
  await main.getByRole('link', { name, exact: true }).first().click();
  await settle(page, 1500);
  await shot(`tab-${name}`, true);
  const controls = await main.locator('button, input, select, textarea').evaluateAll((els) =>
    els
      .filter((e) => e.offsetParent !== null)
      .map((e) => (e.tagName === 'BUTTON' ? `button:${e.textContent?.trim()}` : `${e.tagName.toLowerCase()}:${e.labels?.[0]?.textContent?.trim().slice(0, 40) ?? e.type}`)),
  );
  console.log(`\n=== ${name} === controls: ${JSON.stringify(controls)}`);
  const text = afterTabs(await mainText(page, 20000));
  console.log(text.slice(0, name === 'Reports' || name === 'Activity' ? 3500 : 900));
}

// --- dossier ---------------------------------------------------------------------------------
await main.getByRole('link', { name: 'Reports', exact: true }).first().click();
await settle(page, 1200);
const dl = main.getByRole('button', { name: /dossier/i }).first();
let dossierFile = null;
if (await dl.isVisible().catch(() => false)) {
  const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }).catch(() => null), dl.click()]);
  if (download) {
    dossierFile = path.join(outDir, 'dossier.zip');
    await download.saveAs(dossierFile);
    console.log('\ndossier downloaded:', fs.statSync(dossierFile).size, 'bytes');
  }
  await settle(page, 2000);
  await shot('after-dossier', true);
  console.log('=== REPORTS AFTER DOSSIER ===\n' + afterTabs(await mainText(page, 6000)));
} else {
  console.log('\nno dossier button offered to this role');
}

// A file-verification control, if the role has one.
const fileInput = main.locator('input[type=file]').first();
if (dossierFile && (await fileInput.count())) {
  await fileInput.setInputFiles(dossierFile);
  const verify = main.getByRole('button', { name: /check file|verify/i }).first();
  if (await verify.isVisible().catch(() => false)) await verify.click();
  await settle(page, 2000);
  await shot('verified-file', true);
  console.log('=== AFTER VERIFYING THE DOWNLOADED FILE ===\n' + afterTabs(await mainText(page, 6000)).slice(0, 2500));
}

// --- what the server refuses (same session cookie, direct API calls) ---------------------------
const projectId = await page.evaluate(async (slugUrl) => {
  const slug = slugUrl.split('/projects/')[1].split('/')[0];
  const r = await fetch(`${window.location.origin.replace(':3100', ':8100')}/projects/${slug}`, { credentials: 'include' });
  return r.ok ? (await r.json()).id : null;
}, projectUrl);
console.log('\nproject id', projectId);
const api = context.request;
const origin = { Origin: base };
const probe = async (label, promise) => console.log(`server: ${label} -> ${(await promise).status()}`);
await probe('request satellite data', api.post(`${apiBase}/projects/${projectId}/observations/ingestions`, { headers: origin, data: { start_year: 2021, end_year: 2022, window_start: '01-15', window_end: '03-15' } }));
await probe('add a claim', api.post(`${apiBase}/projects/${projectId}/claims`, { headers: origin, data: { text: 'x', kind: 'area_hectares', value: 1, unit: 'ha' } }));
await probe('upload a document', api.post(`${apiBase}/projects/${projectId}/documents`, { headers: origin, multipart: { file: { name: 'x.txt', mimeType: 'text/plain', buffer: Buffer.from('x') } } }));
await probe('download technical dossier', api.get(`${apiBase}/projects/${projectId}/export/dossier`));
await probe('share the project', api.post(`${apiBase}/projects/${projectId}/grants`, { headers: origin, data: { org_slug: 'demo-government', level: 'view' } }));
await probe('read ledger', api.get(`${apiBase}/projects/${projectId}/ledger`));
await probe("another organisation's private project page", api.get(`${apiBase}/orgs/demo-ngo/projects`));

console.log('org', org, 'url', page.url().replace(base, ''));
printEvents(events);
await browser.close();
