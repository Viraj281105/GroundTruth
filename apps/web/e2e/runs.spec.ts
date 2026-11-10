import { expect, test, type Page, type Response } from '@playwright/test';
import { API, ORG, signInViaApi, skipTour } from './helpers';

/**
 * A run from the UI to the rendered result (#49): browser -> API -> queue -> worker -> engine ->
 * store -> UI, on the real stack (e2e/stack.ts starts the API, a worker and the web app) with
 * simulated data. Nothing here mocks the API. The one fault the failure test injects is the
 * network going away after the run has started.
 *
 * Each test asks for its own specification (its own minimum comparison areas), so tests running
 * side by side never answer one another from the cache.
 */

// Only the owning org's members may start a run; Kariba belongs to the Reference org.
const ORG_SLUG = ORG.operator;
const PROJECT = 'kariba-redd';
const RUN_PAGE = `/app/${ORG_SLUG}/projects/${PROJECT}/run`;

test.beforeEach(async ({ page }, info) => {
  test.skip(info.project.name === 'phone', 'one browser is enough to drive the whole stack');
  await skipTour(page);
  await signInViaApi(page.context(), 'operator');
});

/** Open the run page, optionally ask for a stricter minimum, start, and return the run id. */
async function startRun(page: Page, minDonors?: number): Promise<string> {
  await page.goto(RUN_PAGE);
  await expect(page.getByRole('heading', { name: 'Run an analysis' })).toBeVisible();
  if (minDonors !== undefined) await page.getByLabel('Minimum comparison areas').fill(String(minDonors));
  const submitted: Promise<Response> = page.waitForResponse(
    (r) => r.url().endsWith('/jobs') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Start analysis' }).click();
  const response = await submitted;
  expect(response.status(), 'POST /jobs').toBeLessThan(300);
  return (await response.json()).run_id as string;
}

async function storedRun(page: Page, runId: string): Promise<Record<string, unknown>> {
  const r = await page.request.get(`${API}/runs/${runId}?include_bundle=false`);
  expect(r.status()).toBe(200);
  return (await r.json()) as Record<string, unknown>;
}

test.describe('a run from the UI', () => {
  test('happy path: the result is computed, stored and shown, labelled simulated', async ({ page }) => {
    const runId = await startRun(page);
    await expect(page.getByRole('heading', { name: 'Analysis complete' })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText('Simulated run', { exact: true })).toBeVisible();
    await expect(page.getByText(/^Headline:/)).toBeVisible();
    const run = await storedRun(page, runId);
    expect(run.result_state).toBe('measured');
    expect(run.is_simulated).toBe(true);
  });

  test('refusal: a legitimate outcome, shown as one, not as an error', async ({ page }) => {
    const runId = await startRun(page, 500);
    const outcome = page.locator('[data-outcome="refused"]');
    await expect(outcome).toBeVisible({ timeout: 60_000 });
    await expect(outcome.getByRole('heading', { name: 'The engine declined to produce an estimate' })).toBeVisible();
    await expect(outcome).toContainText(/donors/i); // the engine's own reason
    await expect(outcome).toHaveAttribute('role', 'status'); // a state, never an alert
    // No alert says anything (Next.js keeps an empty route announcer with role="alert" on every page).
    await expect(page.getByRole('alert').filter({ hasText: /\S/ })).toHaveCount(0);
    await expect(page.getByText(/did not finish|could not be reached|error/i)).toHaveCount(0);
    const run = await storedRun(page, runId);
    expect(run.result_state).toBe('refused');
    expect((run.error as { is_refusal: boolean }).is_refusal).toBe(true);
  });

  test('a lower minimum than the case allows is refused before anything runs', async ({ page }) => {
    await page.goto(RUN_PAGE);
    await page.getByLabel('Minimum comparison areas').fill('10');
    await page.getByRole('button', { name: 'Start analysis' }).click();
    const outcome = page.locator('[data-outcome="failed"]');
    await expect(outcome).toBeVisible();
    await expect(outcome).toContainText(/floor|minimum/i);
  });

  test('cancel: a running job stops, and no result is stored', async ({ page }) => {
    test.skip(
      process.env.E2E_EXTERNAL_STACK === '1' && process.env.E2E_WORKER_PAUSES !== '1',
      'needs a worker that pauses before its engine (--pause-before-engine); set E2E_WORKER_PAUSES=1 if it does',
    );
    const runId = await startRun(page, 35);
    await expect(page.getByRole('heading', { name: 'Run in progress' })).toBeVisible();
    // Wait until a worker holds the job (the e2e worker pauses before its engine starts).
    await expect
      .poll(async () => ((await (await page.request.get(`${API}/jobs/${runId}`)).json()) as { status: string }).status, {
        timeout: 20_000,
      })
      .toBe('running');
    await page.getByRole('button', { name: 'Cancel run' }).click();
    await expect(page.locator('[data-outcome="cancelled"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'The run was cancelled' })).toBeVisible();
    const run = await storedRun(page, runId);
    expect(run.status).toBe('cancelled');
    expect(run.has_bundle).toBe(false);
  });

  test('failure: when the API goes away mid-run, the UI says so instead of hanging', async ({ page }) => {
    const runId = await startRun(page, 36);
    await expect(page.getByRole('heading', { name: 'Run in progress' })).toBeVisible();
    // The API becomes unreachable for this browser: its progress stream and status reads fail.
    await page.route('**/jobs/**', (route) => route.abort('connectionrefused'));
    const outcome = page.locator('[data-outcome="lostContact"]');
    await expect(outcome).toBeVisible({ timeout: 60_000 });
    await expect(outcome.getByRole('heading', { name: 'Lost contact with the analysis service' })).toBeVisible();
    await expect(outcome).toContainText(runId); // the run exists and may still finish
    await expect(page.getByRole('heading', { name: 'Analysis complete' })).toHaveCount(0); // no fake success
  });
});
