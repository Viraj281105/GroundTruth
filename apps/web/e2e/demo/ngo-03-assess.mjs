// NGO journey, step 3: read the ingested observations, promote extracted statements to claims,
// read the outcomes, then download the dossier. Stage is the first argument:
//   observe | promote | verify | report
import fs from 'node:fs';
import path from 'node:path';
import { open, signIn, settle, printEvents, mainText, base } from './lib.mjs';

const stage = process.argv[2] ?? 'observe';
const { browser, page, events, shot, outDir } = await open({ name: `ngo-03-${stage}` });
const main = page.locator('main');
const tab = async (name) => {
  await main.getByRole('link', { name, exact: true }).first().click();
  await settle(page, 1500);
};
const afterTabs = (text) => text.split('\nActivity\n').slice(1).join('\nActivity\n');

await signIn(page, 'ngo');
await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'Projects', exact: true }).click();
await settle(page);
await main.getByRole('link', { name: /Sahyadri Foothills/ }).first().click();
await settle(page, 1500);

if (stage === 'observe') {
  await shot('overview', true);
  console.log('=== OVERVIEW ===\n' + (await mainText(page, 7000)));
  await tab('Earth Observation');
  await shot('observation', true);
  console.log('=== EARTH OBSERVATION ===\n' + afterTabs(await mainText(page, 12000)).split('Your requests').slice(1).join(''));
  const table = main.getByRole('button', { name: 'Table', exact: true }).first();
  if (await table.isVisible().catch(() => false)) {
    await table.click();
    await page.waitForTimeout(500);
    await shot('observation-table', true);
    console.log('=== TABLE ===\n' + afterTabs(await mainText(page, 14000)).split('Vegetation index series').slice(1).join(''));
  }
}

if (stage === 'promote') {
  await tab('Evidence');
  await main.getByRole('button', { name: /extracted statements/i }).first().click();
  await settle(page, 1500);
  const count = await main.getByRole('button', { name: 'Review and add as claim' }).count();
  console.log('candidates:', count);
  for (let i = 0; i < count; i++) {
    // The list re-renders after each promotion; always take the first remaining button.
    const button = main.getByRole('button', { name: 'Review and add as claim' }).first();
    if (!(await button.isVisible().catch(() => false))) break;
    await button.click();
    await page.waitForTimeout(600);
    if (i === 0) {
      await shot('review-form', true);
      console.log('=== REVIEW FORM ===\n' + afterTabs(await mainText(page, 9000)).split('Extracted statements').slice(1).join('').slice(0, 2500));
      console.log('buttons:', JSON.stringify(await page.getByRole('button').evaluateAll((els) => els.map((b) => b.textContent?.trim()).filter(Boolean))));
    }
    const confirm = page.getByRole('button', { name: /^(Add claim|Add as claim|Save claim|Confirm|Add to claims)/ }).first();
    await confirm.click();
    await settle(page, 1200);
  }
  await shot('promoted', true);
  console.log('=== AFTER PROMOTION ===\n' + afterTabs(await mainText(page, 6000)).split('Extracted statements').slice(1).join('').slice(0, 3000));
}

if (stage === 'verify') {
  await tab('Verification');
  await shot('verification', true);
  console.log('=== VERIFICATION ===\n' + afterTabs(await mainText(page, 16000)));
}

if (stage === 'report') {
  await tab('Reports');
  await shot('reports', true);
  console.log('=== REPORTS ===\n' + afterTabs(await mainText(page, 8000)));
  console.log('buttons:', JSON.stringify(await main.getByRole('button').evaluateAll((els) => els.map((b) => b.textContent?.trim()).filter(Boolean))));
  console.log('links:', JSON.stringify(await main.locator('a').evaluateAll((els) => els.map((a) => `${a.textContent?.trim()} -> ${a.getAttribute('href')}`).filter((t) => !/\/projects\/[^/]+\/(overview|observation|climate|evidence|verification|reports|activity)$/.test(t)))));
  const dl = main.getByRole('button', { name: /dossier|download/i }).first();
  if (await dl.isVisible().catch(() => false)) {
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }).catch(() => null), dl.click()]);
    if (download) {
      const file = path.join(outDir, download.suggestedFilename());
      await download.saveAs(file);
      console.log('downloaded', file, fs.statSync(file).size, 'bytes');
    } else console.log('no download event');
    await settle(page, 2500);
    await shot('after-download', true);
    console.log('=== AFTER DOWNLOAD ===\n' + afterTabs(await mainText(page, 8000)));
  }
}

console.log('url', page.url().replace(base, ''));
printEvents(events);
await browser.close();
