import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { ORG, signInViaApi, skipTour } from './helpers';
import type { Persona } from './seed';

test.beforeEach(async ({ page }) => {
  await skipTour(page);
});

/**
 * Moderate findings accepted for slice 1, as `rule@page label`. Any moderate finding NOT listed fails, so a new
 * one is caught; delete an entry once its fix lands (an unused entry is only reported, not failed).
 *  - heading-order: project workspace pages render panels (h3) directly under the page h1; the panels are shared
 *    and frozen, the dashboards get a screen-reader h2 per region but the workspace layer does not yet.
 *  - landmark-unique: the funder dashboard's Portfolio region and the panel inside it share one label.
 */
const KNOWN_MODERATE = new Set([
  'heading-order@workspace overview',
  'heading-order@workspace climate',
  'heading-order@workspace evidence',
  'landmark-unique@funder dashboard',
]);

/** Serious and critical violations fail the run; so does any moderate finding outside KNOWN_MODERATE. */
async function expectNoSeriousViolations(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze();
  const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  const summary = bad.map((v) => [`${v.impact} ${v.id}: ${v.help}`, ...v.nodes.slice(0, 4).map((n) => `    ${n.target.join(' ')}`)].join('\n')).join('\n');
  expect(bad, `${label}\n${summary}`).toEqual([]);
  const newModerate = results.violations.filter((v) => v.impact === 'moderate' && !KNOWN_MODERATE.has(`${v.id}@${label}`)).map((v) => v.id);
  expect(newModerate, `${label}: moderate findings not in KNOWN_MODERATE`).toEqual([]);
}

test('login page', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expectNoSeriousViolations(page, 'login');
});

const DASHBOARDS: Array<[Persona, boolean]> = [
  ['ngo', true],
  ['auditor', true],
  ['funder', false],
  ['government', false],
];

for (const [persona, required] of DASHBOARDS) {
  test(`${persona} dashboard${required ? '' : ' (optional persona)'}`, async ({ page }) => {
    await signInViaApi(page.context(), persona);
    await page.goto(`/app/${ORG[persona]}/dashboard`);
    await expect(page.locator('[data-persona-question]')).toBeVisible();
    await expect(page.locator('[data-panel]').last()).toBeVisible();
    await expectNoSeriousViolations(page, `${persona} dashboard`);
  });
}

for (const tab of ['overview', 'climate', 'evidence']) {
  test(`project workspace: ${tab}`, async ({ page }) => {
    await signInViaApi(page.context(), 'auditor');
    await page.goto(`/app/${ORG.auditor}/projects/kariba-redd/${tab}`);
    await expect(page.getByRole('heading', { level: 1, name: 'Kariba REDD+ Project' })).toBeVisible();
    await expect(page.locator('main h2, main h3').first()).toBeVisible();
    await expectNoSeriousViolations(page, `workspace ${tab}`);
  });
}
