// NGO journey, step 2: upload a document, read the extracted statements, then request
// satellite observations. Pass "request" as the first argument to submit the request.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { open, signIn, settle, printEvents, mainText, base } from './lib.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const slug = process.env.DEMO_PROJECT ?? 'sahyadri-foothills-restoration-demonstration';
const stage = process.argv[2] ?? 'upload';
const { browser, page, events, shot } = await open({ name: `ngo-02-${stage}` });
const main = page.locator('main');
const tab = async (name) => {
  await main.getByRole('link', { name, exact: true }).first().click();
  await settle(page, 1200);
};

const org = await signIn(page, 'ngo');
await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'Projects', exact: true }).click();
await settle(page);
await shot('projects-list', true);
await main.getByRole('link', { name: /Sahyadri Foothills/ }).first().click();
await settle(page, 1200);

if (stage === 'upload') {
  await tab('Evidence');
  await page.locator('input[type=file]').first().setInputFiles(path.join(here, 'fixtures', 'demo-project-design-note.md'));
  await page.getByRole('button', { name: 'Upload document' }).click();
  await settle(page, 2000);
  await shot('uploaded', true);
  console.log('=== after upload ===\n' + (await mainText(page, 6000)).split('Activity\n').slice(1).join('Activity\n'));
  const buttons = await main.getByRole('button').evaluateAll((els) => els.map((b) => b.textContent?.trim()));
  console.log('buttons:', JSON.stringify(buttons));
  const view = main.getByRole('button', { name: /extracted statements/i }).first();
  if (await view.isVisible().catch(() => false)) {
    await view.click();
    await settle(page, 2000);
    await shot('extracted', true);
    console.log('=== extracted ===\n' + (await mainText(page, 9000)).split('Project documents').slice(1).join('Project documents'));
    console.log('buttons:', JSON.stringify(await main.getByRole('button').evaluateAll((els) => els.map((b) => b.textContent?.trim()))));
  }
}

if (stage === 'form' || stage === 'request') {
  await tab('Earth Observation');
  await main.getByText('Choose my own dates').click();
  await main.getByText('Advanced options').click();
  await page.waitForTimeout(500);
  await shot('request-form', true);
  const fields = await main.locator('input, select').evaluateAll((els) =>
    els.map((e) => ({ tag: e.tagName, type: e.type, name: e.name, id: e.id, value: e.value, label: e.labels?.[0]?.textContent?.trim() })),
  );
  console.log(JSON.stringify(fields, null, 0));
  if (stage === 'request') {
    await main.getByLabel('Season starts (MM-DD)').fill('01-15');
    await main.getByLabel('Season ends (MM-DD)').fill('03-15');
    for (const name of [/^EVI/, /^NDMI/, /^NBR/]) await main.getByRole('checkbox', { name }).check();
    await main.getByLabel(/Cloud limit/).fill('20');
    await main.getByLabel(/Scenes per year/).fill('2');
    await shot('request-filled', true);
    await main.getByRole('button', { name: 'Request satellite data' }).click();
    await settle(page, 2500);
    await shot('request-submitted', true);
    console.log('=== after request ===\n' + (await mainText(page, 6000)).split('Your requests').slice(1).join('Your requests'));
  }
}

if (stage === 'status') {
  await tab('Earth Observation');
  await shot('status', true);
  console.log((await mainText(page, 9000)).split('Your requests').slice(1).join('Your requests'));
}

console.log('url', page.url().replace(base, ''), 'org', org);
printEvents(events);
await browser.close();
