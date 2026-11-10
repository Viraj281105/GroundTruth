// NGO journey, step 4: share the project from the Sharing page. First argument: look | share
import { open, signIn, settle, printEvents, mainText, base } from './lib.mjs';

const stage = process.argv[2] ?? 'look';
const { browser, page, events, shot } = await open({ name: `ngo-04-${stage}` });
const main = page.locator('main');
await signIn(page, 'ngo');
await page.getByRole('navigation', { name: 'Main', exact: true }).getByRole('link', { name: 'Sharing', exact: true }).click();
await settle(page, 1200);
await shot('sharing', true);
console.log('=== SHARING ===\n' + (await mainText(page, 5000)));
const fields = await main.locator('input, select, textarea, button').evaluateAll((els) =>
  els.map((e) => ({ tag: e.tagName, type: e.type, label: e.labels?.[0]?.textContent?.trim() ?? e.getAttribute('aria-label'), text: e.tagName === 'BUTTON' ? e.textContent?.trim() : undefined, options: e.tagName === 'SELECT' ? [...e.options].map((o) => o.textContent) : undefined })),
);
console.log(JSON.stringify(fields));

if (stage === 'share') {
  for (const [org, level] of [['demo-funder', 'view'], ['demo-auditor', 'audit']]) {
    await main.getByLabel('Organization slug').fill(org);
    await main.getByLabel('Level').selectOption(level);
    await main.getByRole('button', { name: 'Grant access' }).click();
    await settle(page, 1500);
    console.log(`--- after sharing with ${org} (${level}) ---`);
    console.log(await mainText(page, 2500));
  }
  // What does a typo look like to the user?
  await main.getByLabel('Organization slug').fill('no-such-organization');
  await main.getByRole('button', { name: 'Grant access' }).click();
  await settle(page, 1200);
  console.log('--- unknown organization ---');
  console.log(await mainText(page, 2500));
  await shot('shared', true);
}
console.log('url', page.url().replace(base, ''));
printEvents(events);
await browser.close();
