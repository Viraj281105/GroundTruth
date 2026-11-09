import { expect, test, type Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { API, HAS_KARIBA_CACHES, ORG, WEB, openDashboard, screenshot, signInViaApi, signInViaForm, skipTour, zipEntry } from './helpers';

test.beforeEach(async ({ page }) => {
  await skipTour(page);
});

const ENGINE_LEVEL = 'Level 2 · Contextual intelligence';

/** Phone layout hides the sidebar; every journey navigates by links that exist in both layouts. */
async function openKariba(page: Page, persona: keyof typeof ORG, tab: string): Promise<void> {
  await page.goto(`/app/${ORG[persona]}/projects`);
  await page.getByRole('link', { name: 'Kariba REDD+ Project' }).click();
  await expect(page).toHaveURL(/\/projects\/kariba-redd\/overview$/);
  await page.getByRole('link', { name: tab, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/kariba-redd/${tab.toLowerCase()}$`));
}

test.describe('ngo journey', () => {
  test('sign in, dashboard, climate, reports', async ({ page }, info) => {
    await signInViaForm(page, 'ngo');
    await expect(page).toHaveURL(/\/app\/demo-ngo\/dashboard$/);
    await expect(page.locator('[data-persona-question]')).toBeVisible();

    test.skip(!HAS_KARIBA_CACHES, 'Kariba real-data caches (data/processed/stac_cache, climate_cache) are absent');
    await expect(page.getByText(ENGINE_LEVEL).first()).toBeVisible();
    await expect(page.locator('[data-dimension-id]')).toHaveCount(8);
    const rec = page.locator('[data-recommendation-id="acquire_reference_series"]');
    await expect(rec).toBeVisible();
    await expect(rec).toContainText(/reference areas/i);
    await expect(rec.getByText('Why')).toBeVisible();
    await expect(rec.locator('h4 ~ div')).not.toBeEmpty();
    await screenshot(page, info, 'ngo-dashboard', { phone: true });

    // Workspace overview, then the Climate tab with the real series and its two missing months.
    await page.goto('/app/demo-ngo/projects/kariba-redd/overview');
    await expect(page.getByText(ENGINE_LEVEL).first()).toBeVisible();
    await screenshot(page, info, 'kariba-overview');
    await openKariba(page, 'ngo', 'Climate');
    await expect(page.getByRole('heading', { name: 'Rainfall and drought' })).toBeVisible();
    await expect(page.getByRole('row', { name: /^2019 .*Drought \(severe drought\)/ })).toBeVisible();
    for (const year of ['2022', '2023']) {
      await expect(page.getByRole('row', { name: new RegExp(`^${year} no data .*11/12 \\(incomplete\\)`) })).toBeVisible();
    }
    const missing = page.getByLabel('Missing months');
    await expect(missing).toContainText('2022-07');
    await expect(missing).toContainText('2023-12');

    // Reports: an observed project with no completed run has no monitoring report. The tab must say so
    // instead of offering the legacy simulated-run PDF as if it described Kariba.
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    await expect(page.getByText('The monitoring report becomes available after a completed run.')).toBeVisible();
    await expect(page.getByRole('button', { name: /Download PDF/ })).toHaveCount(0);
  });
});

test.describe('funder journey', () => {
  test('portfolio row, inconclusive attribution, review language', async ({ page }, info) => {
    await signInViaApi(page.context(), 'funder');
    await openDashboard(page, 'funder');
    test.skip(!HAS_KARIBA_CACHES, 'Kariba real-data caches are absent');

    const main = page.locator('main');
    const row = main.getByRole('row', { name: /Kariba REDD\+ Project/ }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(ENGINE_LEVEL);
    await expect(row).toContainText('Inconclusive');
    // No totals, no scores, and no reported funding unless an organization reported it.
    await expect(main).not.toContainText(/\b(total|score)\b/i);
    await expect(main.getByText(/reported by/i)).toHaveCount(0);
    const cells = await row.getByRole('cell').allInnerTexts();
    const header = (await main.getByRole('columnheader').allInnerTexts()).findIndex((h) => /reported funding/i.test(h));
    expect(header).toBeGreaterThanOrEqual(0);
    expect(cells[header]?.trim() ?? '').not.toMatch(/\d/);

    const attention = page.locator('[data-panel="needs-attention"], section[aria-label*="attention" i]').first();
    await expect(attention).toContainText(/prompts for review/i);
    await expect(attention).toContainText(/suggested review step/i);
    await expect(main).not.toContainText(/fraud|wrongdoing|violation|misconduct|non-?compliant/i);
    await screenshot(page, info, 'funder-dashboard');
  });
});

test.describe('auditor journey', () => {
  test('evidence inventory carries checksums and scene ids; dossier ZIP is valid', async ({ page }, info) => {
    await signInViaApi(page.context(), 'auditor');
    await openDashboard(page, 'auditor');
    await screenshot(page, info, 'auditor-dashboard', { phone: true });
    test.skip(!HAS_KARIBA_CACHES, 'Kariba real-data caches are absent');

    await openKariba(page, 'auditor', 'Evidence');
    const main = page.locator('main');
    await expect(main.getByText('Boundary checksum')).toBeVisible();
    await expect(main.getByText(/S2[AB]_MSIL2A_\d{8}T\d{6}/).first()).toBeVisible();
    await expect(main.getByText(/\b[0-9a-f]{64}\b/).first()).toBeVisible();

    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Download dossier/ }).click();
    const download = await downloadPromise;
    const path = await download.path();
    const { readFileSync } = await import('node:fs');
    const buf = readFileSync(path!);
    expect(buf.subarray(0, 4).toString('hex')).toBe('504b0304');
    const manifest = zipEntry(buf, 'manifest.json');
    expect(manifest, 'manifest.json in the dossier').not.toBeNull();
    const parsed = JSON.parse(manifest!.toString('utf8')) as unknown;
    expect(parsed).toBeTruthy();
  });
});

test.describe('government journey', () => {
  test('regional map region and honest regional climate state', async ({ page }, info) => {
    await signInViaApi(page.context(), 'government');
    await openDashboard(page, 'government');
    await expect(page.locator('[data-persona-question]')).toHaveText('Which landscapes need attention?');
    await expect(page.getByRole('heading', { name: 'Project footprints' })).toBeVisible();
    const map = page.locator('[data-panel="map"]');
    await expect(map.locator('canvas, [role="status"]').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Regional district climate summaries are not served by the API yet.')).toBeVisible();
    // No invented numbers: the district climate region carries no digits at all.
    const spi = page.locator('[data-panel="regional-spi"]');
    await expect(spi).toBeVisible();
    expect(await spi.innerText()).not.toMatch(/\d/);
    await screenshot(page, info, 'government-dashboard');
  });
});

test.describe('cross-organization denial', () => {
  test('funder gets the not-found page and a 404 from the API', async ({ page }, info) => {
    await signInViaApi(page.context(), 'funder');
    const res = await page.goto('/app/demo-ngo/projects');
    expect(res?.status()).toBe(404);
    await expect(page.getByText('This page could not be found')).toBeVisible();
    await expect(page.getByText('Kariba')).toHaveCount(0);
    await screenshot(page, info, 'cross-org-denied');

    // The same boundary on the API, called from the browser with the funder's session.
    const org = await page.request.get(`${API}/orgs/demo-ngo/projects`);
    expect(org.status()).toBe(404);
    const members = await page.request.get(`${API}/orgs/demo-ngo/members`);
    expect(members.status()).toBe(404);
  });

  test('a project nobody shared with the auditor answers 404 from every project endpoint', async ({ page }) => {
    await signInViaApi(page.context(), 'auditor');
    for (const leaf of ['', '/assessment', '/climate', '/evidence-inventory', '/export/dossier']) {
      const r = await page.request.get(`${API}/projects/kariba-redd-benchmark${leaf}`);
      expect(r.status(), leaf || 'project').toBe(404);
    }
    await page.goto('/app/demo-auditor/projects/kariba-redd-benchmark/overview');
    await expect(page.getByText('This page could not be found')).toBeVisible();
  });
});

test.describe('sign-in redirects', () => {
  test('signed-out deep link goes to login with next and returns after sign-in', async ({ page }) => {
    await page.goto('/app/demo-ngo/dashboard');
    await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fdemo-ngo%2Fdashboard$/);
    await signInViaForm(page, 'ngo', '/app/demo-ngo/dashboard');
    await expect(page).toHaveURL(/\/app\/demo-ngo\/dashboard$/);
    await expect(page.locator('[data-persona-question]')).toBeVisible();
  });

  for (const evil of ['//evil.com', 'https://evil.com/app', '/\\evil.com', '/app/../../evil']) {
    test(`next=${evil} lands on /app, never off-site`, async ({ page }) => {
      await signInViaForm(page, 'ngo', evil);
      await page.waitForURL((u) => u.pathname.startsWith('/app'));
      expect(new URL(page.url()).origin).toBe(new URL(WEB).origin);
      await expect(page).toHaveURL(/\/app\/demo-ngo\/dashboard$/);
    });
  }

  test('sign out ends the session and protected pages redirect again', async ({ page }) => {
    await signInViaApi(page.context(), 'ngo');
    await openDashboard(page, 'ngo');
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await expect(page).toHaveURL(new RegExp(`^${WEB.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/?$`));
    await page.goto('/app/demo-ngo/dashboard');
    await expect(page).toHaveURL(/\/login\?next=/);
    const me = await page.request.get(`${API}/auth/me`);
    expect((await me.json()).user).toBeNull();
  });
});

test.describe('organization switching', () => {
  test('switcher and the server-side deep link both change the active org', async ({ page }, info) => {
    await signInViaApi(page.context(), 'ngo');
    const secondName = `E2E Second NGO ${randomBytes(3).toString('hex')}`;
    const created = await page.request.post(`${API}/orgs`, {
      data: { name: secondName, type: 'ngo' },
      headers: { Origin: WEB },
    });
    expect(created.status()).toBe(201);
    const second = (await created.json()).slug as string;
    const active = async () => (await (await page.request.get(`${API}/auth/me`)).json()).active_organization?.slug as string;

    await page.goto('/app/demo-ngo/dashboard');
    if (info.project.name === 'phone') await page.getByRole('button', { name: 'More' }).click();
    await page.getByRole('button', { name: /Demo NGO/ }).locator('visible=true').first().click();
    await page.getByRole('group', { name: 'Organizations' }).getByRole('button', { name: new RegExp(secondName) }).click();
    await expect(page).toHaveURL(new RegExp(`/app/${second}/dashboard$`));
    expect(await active()).toBe(second);

    // Deep link to the other org: the layout switches the active org on the server (CSRF-origin path).
    await page.goto('/app/demo-ngo/dashboard');
    await expect(page.locator('[data-persona-question]')).toBeVisible();
    expect(await active()).toBe('demo-ngo');
    await page.goto(`/app/${second}/dashboard`);
    await expect(page.locator('main')).toBeVisible();
    expect(await active()).toBe(second);
  });
});

test.describe('simulated data', () => {
  test('benchmark is labelled SIMULATED and never in a real portfolio list', async ({ page }) => {
    await signInViaApi(page.context(), 'ngo');
    await page.goto('/app/demo-ngo/projects');
    const benchmarkRow = page.locator('tr', { hasText: 'SIMULATED benchmark' });
    await expect(benchmarkRow).toContainText('Simulated data');
    await page.getByRole('link', { name: /SIMULATED benchmark/ }).click();
    await expect(page.getByRole('status').filter({ hasText: /Simulated data/i }).first()).toBeVisible();
    await expect(page.getByText(/Every number here comes from a simulated test fixture/).first()).toBeVisible();
    await expect(page.getByText(/\[SIMULATED DATA\]/).first()).toBeVisible();

    // The funder holds a grant on the benchmark: it must appear only in the labelled simulated section.
    await page.context().clearCookies();
    await signInViaApi(page.context(), 'funder');
    await openDashboard(page, 'funder');
    const sim = page.locator('[data-section="simulated"]');
    await expect(sim).toContainText('SIMULATED benchmark');
    await expect(sim.getByText('Simulated data').first()).toBeVisible();
    const real = await page.locator('main table').evaluateAll((ts) => ts.filter((t) => !t.closest('[data-section="simulated"]')).map((t) => (t as HTMLElement).innerText));
    expect(real.length).toBeGreaterThan(0);
    for (const text of real) expect(text).not.toMatch(/benchmark/i);
    const api = await page.request.get(`${API}/orgs/demo-funder/portfolio`);
    const body = await api.json();
    expect(JSON.stringify(body.projects)).not.toContain('kariba-redd-benchmark');
    expect(JSON.stringify(body.simulated)).toContain('kariba-redd-benchmark');
  });
});
