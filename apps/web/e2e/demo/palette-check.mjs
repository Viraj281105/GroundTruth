// Uses the command palette (Ctrl+K) the way the welcome tour tells a new user to, and reports
// where each entry lands. Run with a persona: node e2e/demo/palette-check.mjs government
import { open, signIn, settle, printEvents, base } from './lib.mjs';

const persona = process.argv[2] ?? 'government';
const { browser, page, events, shot } = await open({ name: `palette-${persona}` });
const org = await signIn(page, persona);
const home = `${base}/app/${org}/dashboard`;

async function viaPalette(query, label) {
  await page.goto(home);
  await settle(page);
  await page.keyboard.press('Control+k');
  const box = page.getByRole('combobox', { name: 'Command' });
  await box.waitFor({ state: 'visible', timeout: 5000 });
  await box.fill(query);
  await page.waitForTimeout(300);
  const options = await page.getByRole('option').allInnerTexts();
  const target = label ? page.getByRole('option', { name: label }).first() : page.getByRole('option').first();
  if (!(await target.isVisible().catch(() => false))) {
    console.log(`?? "${query}": no option ${label ?? ''}; options = ${JSON.stringify(options.slice(0, 6))}`);
    await page.keyboard.press('Escape');
    return;
  }
  const chosen = (await target.innerText()).replace(/\s+/g, ' ');
  await target.click();
  await settle(page, 800);
  const body = await page.locator('body').innerText();
  const notFound = /could not be found|not found|\b404\b/i.test(body);
  const h1 = await page.locator('h1').first().innerText({ timeout: 1500 }).catch(() => '-');
  console.log(`${notFound ? '!!' : 'ok'} "${query}" -> [${chosen}] -> ${page.url().replace(base, '')} | h1: ${h1.slice(0, 60)}${notFound ? ' | NOT FOUND' : ''}`);
  await shot(`q-${query || 'empty'}-${chosen}`);
}

await viaPalette('kariba', /Kariba REDD\+ Project/);
await viaPalette('', 'Reports');
await viaPalette('', 'Evidence Library');
await viaPalette('', 'Projects');
await viaPalette('', 'How it works');
await viaPalette('', 'Overview');
await viaPalette('compare kariba and mikoko');
await viaPalette('sahyadri');
printEvents(events);
await browser.close();
