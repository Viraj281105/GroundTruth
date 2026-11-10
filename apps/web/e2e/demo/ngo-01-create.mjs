// NGO journey, step 1: sign in, create a project from the sidebar with an uploaded boundary,
// then look at every project tab the way a first-time user would.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { open, signIn, settle, printEvents, mainText } from './lib.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const { browser, page, events, shot } = await open({ name: 'ngo-01-create' });

const org = await signIn(page, 'ngo');
await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'New project' }).click();
await settle(page);

// Submit empty first: what does a user who clicks too early see?
await page.getByRole('button', { name: 'Create project' }).click();
await page.waitForTimeout(500);
await shot('empty-submit');
console.log('--- after empty submit ---\n' + (await mainText(page, 900)));

await page.getByLabel('Project name').fill('Sahyadri Foothills Restoration (demonstration)');
await page.getByLabel('Country').fill('India');
await page.getByLabel('Ecosystem').fill('dry deciduous hill forest');
await page.getByLabel('Intervention').fill('restoration');
await page.getByLabel('Treatment start year').fill('2021');
await page.getByLabel('Boundary file').setInputFiles(path.join(here, 'fixtures', 'demo-boundary-pune.geojson'));
await shot('form-filled');
await page.getByRole('button', { name: 'Create project' }).click();
await page.waitForURL(/\/projects\/(?!new)[^/]+/, { timeout: 20000 }).catch(() => {});
await settle(page, 1500);
console.log('after create:', page.url());
await shot('created', true);
console.log('--- project landing ---\n' + (await mainText(page, 2500)));

const tabs = await page.locator('main a').evaluateAll((els) =>
  els.map((a) => ({ href: a.getAttribute('href'), text: a.textContent?.trim() })).filter((a) => a.href?.includes('/projects/')),
);
console.log('links:', JSON.stringify(tabs));
for (const name of ['Earth Observation', 'Climate', 'Evidence', 'Verification', 'Reports', 'Activity']) {
  await page.getByRole('link', { name, exact: true }).first().click();
  await settle(page, 1200);
  await shot(`tab-${name}`, true);
  console.log(`\n=== ${name} (${page.url().replace(/^.*\/projects\//, '')}) ===\n` + (await mainText(page, 2200)));
}
console.log('org', org);
printEvents(events);
await browser.close();
