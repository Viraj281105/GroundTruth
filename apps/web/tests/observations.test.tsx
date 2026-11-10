import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ObservationIngestionPanel } from '../src/features/projects/ObservationIngestionPanel';
import { EvidenceGuidance } from '../src/features/projects/EvidenceGuidance';
import { cancelIngestion, fetchIngestions, requestIngestion } from '../src/features/projects/observations.client';
import {
  defaultForm,
  failureMessage,
  formatElapsed,
  formatMonthDay,
  ingestionError,
  isActive,
  isFinal,
  paramsSummary,
  statusInfo,
  summariseResult,
  validateForm,
  type IngestionList,
  type IngestionView,
} from '../src/features/projects/observations.model';
import { lifecycleSteps, type LifecycleInput } from '../src/components/panels/lifecycle.model';
import { inventoryFull } from './panels/fixtures';

vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }), usePathname: () => '/x' }));

const limits: IngestionList['limits'] = {
  first_year: 2017,
  last_year: 2025,
  max_years: 8,
  max_total_scenes: 24,
  min_resolution_m: 20,
  max_resolution_m: 500,
  max_grid_pixels: 4_000_000,
  coverage_threshold_pct: 95,
  indicators: ['ndvi', 'evi', 'ndmi', 'nbr'],
  default_indicators: ['ndvi'],
};

const params = { start_year: 2021, end_year: 2025, window_start: '06-01', window_end: '06-30', max_cloud_cover: 25, indicators: ['ndvi', 'evi'], resolution_m: 100, max_scenes_per_year: 3, platform: 'sentinel-2' };

const year = (y: number, state: 'observed' | 'partial_coverage' | 'no_usable_data', over: Record<string, unknown> = {}) => ({
  year: y,
  state,
  n_scenes: state === 'no_usable_data' ? 0 : 3,
  scene_ids: [],
  acquisition_dates: state === 'no_usable_data' ? [] : ['2022-06-04'],
  contributing_tiles: state === 'no_usable_data' ? [] : ['35KQV'],
  aoi_coverage_pct: state === 'no_usable_data' ? null : state === 'partial_coverage' ? 61.5 : 100,
  clear_pixel_fraction: null,
  is_spatially_complete: state === 'observed',
  values: state === 'no_usable_data' ? { ndvi: null, evi: null } : { ndvi: 0.4567, evi: 0.2 },
  ...over,
});

const ing = (over: Partial<IngestionView> = {}): IngestionView => ({
  id: 'i1',
  project_id: 'p1',
  status: 'queued',
  status_detail: null,
  error_code: null,
  params,
  requested_by: 'u1',
  created_at: '2026-11-09T10:00:00Z',
  started_at: null,
  finished_at: null,
  age_seconds: 30,
  waiting_hint: null,
  result: null,
  ledger_record_id: null,
  ...over,
});

const result = (years: ReturnType<typeof year>[], over: Record<string, unknown> = {}) =>
  ({
    catalog_url: 'https://catalog.example/stac',
    platform: 'sentinel-2',
    collection: 'sentinel-2-l2a',
    bbox: [],
    years_requested: [2021, 2022, 2023, 2024, 2025],
    years,
    coverage: { threshold_pct: 95, complete_years: [2021, 2023, 2025], partial_years: [], years_without_data: [2022, 2024] },
    stored_bundles: { ndvi: { file: 'ndvi_p1.json', sha256: 'abcdef0123456789abcdef' } },
    limitations: ['Cloud cover can hide the ground.'],
    code_version: 'v1.2.3',
    method: 'median composite',
    ...over,
  }) as unknown as IngestionView['result'];

const list = (over: Partial<IngestionList> = {}): IngestionList => ({ project_id: 'p1', enabled: true, active: false, limits, ingestions: [], explanation: 'You can ask GroundTruth to read Sentinel-2 images for your boundary.', ...over });
const render = (l: IngestionList, canEdit = true, reason: string | null = null) =>
  renderToStaticMarkup(<ObservationIngestionPanel projectId="p1" initial={l} canEdit={canEdit} blockedReason={reason} />);

describe('form defaults and validation', () => {
  it('defaults to the last six years, June, 25% cloud, 100 m, NDVI only', () => {
    const f = defaultForm(limits);
    expect(f).toMatchObject({ startYear: '2020', endYear: '2025', season: 'june', windowStart: '06-01', windowEnd: '06-30', maxCloud: '25', resolution: '100', scenesPerYear: '3', indicators: ['ndvi'] });
    expect(validateForm(f, limits).request).toMatchObject({ start_year: 2020, end_year: 2025, resolution_m: 100, indicators: ['ndvi'] });
  });
  it('shrinks the default to fit tight limits', () => {
    const f = defaultForm({ ...limits, max_years: 3, max_total_scenes: 4, first_year: 2024 });
    expect(f.startYear).toBe('2024');
    // two years (2024-2025) x 2 scenes = 4, exactly the limit: the largest default that still fits
    expect(f.scenesPerYear).toBe('2');
    expect(validateForm(f, { ...limits, max_years: 3, max_total_scenes: 4, first_year: 2024 }).errors).toEqual({});
  });
  it('flags bad years, order and span', () => {
    const f = defaultForm(limits);
    expect(validateForm({ ...f, startYear: '2010' }, limits).errors.startYear).toContain('2017');
    expect(validateForm({ ...f, endYear: '2030' }, limits).errors.endYear).toContain('2025');
    expect(validateForm({ ...f, startYear: '2024', endYear: '2022' }, limits).errors.endYear).toContain('before');
    expect(validateForm({ ...f, startYear: '2017', endYear: '2025' }, limits).errors.years).toContain('at most 8');
    expect(validateForm({ ...f, startYear: 'abc' }, limits).errors.startYear).toBeTruthy();
  });
  it('checks the season window', () => {
    const f = defaultForm(limits);
    expect(validateForm({ ...f, windowStart: '13-01' }, limits).errors.windowStart).toBeTruthy();
    expect(validateForm({ ...f, windowEnd: '02-30' }, limits).errors.windowEnd).toBeTruthy();
    expect(validateForm({ ...f, windowStart: '07-01', windowEnd: '06-01' }, limits).errors.windowEnd).toContain('after it starts');
  });
  it('checks cloud, resolution and the total scene budget', () => {
    const f = defaultForm(limits);
    expect(validateForm({ ...f, maxCloud: '90' }, limits).errors.maxCloud).toBeTruthy();
    expect(validateForm({ ...f, maxCloud: '' }, limits).errors.maxCloud).toBeTruthy();
    expect(validateForm({ ...f, resolution: '10' }, limits).errors.resolution).toContain('20 and 500');
    expect(validateForm({ ...f, resolution: '600' }, limits).errors.resolution).toBeTruthy();
    const r = validateForm({ ...f, scenesPerYear: '5' }, limits); // 5 x 6 years = 30 > 24
    expect(r.errors.scenesPerYear).toContain('30 scenes');
    expect(r.request).toBeNull();
  });
  it('always keeps NDVI and drops indicators the server does not allow', () => {
    const f = { ...defaultForm(limits), indicators: ['evi', 'bogus'] };
    expect(validateForm(f, limits).request?.indicators).toEqual(['ndvi', 'evi']);
  });
});

describe('status copy and helpers', () => {
  it('labels every status and never says collected/ingested before a final state', () => {
    for (const s of ['queued', 'running'] as const) {
      const i = statusInfo(s);
      expect(i.explanation.toLowerCase()).not.toMatch(/ingested|collected\b(?! yet)/);
      expect(isActive(s)).toBe(true);
    }
    expect(statusInfo('partial').label).toBe('INCOMPLETE');
    expect(statusInfo('failed').tone).toBe('danger');
    expect(isFinal('cancelled')).toBe(true);
    expect(isFinal('running')).toBe(false);
  });
  it('formats elapsed time, month-day, params and failures', () => {
    expect(formatElapsed(20)).toBe('under a minute');
    expect(formatElapsed(65 * 60)).toBe('1 h 5 min');
    expect(formatElapsed(null)).toBe('unknown time');
    expect(formatMonthDay('06-01')).toBe('1 Jun');
    expect(paramsSummary(params)).toContain('Years 2021–2025');
    expect(paramsSummary(params)).toContain('NDVI, EVI');
    expect(failureMessage({ status_detail: 'No scenes were found.', error_code: 'no_scenes' })).toBe('No scenes were found. (Error code: no_scenes.)');
    expect(failureMessage({ status_detail: null, error_code: null })).toBe('The request did not finish.');
  });
  it('reads the API error shape and falls back to plain sentences', () => {
    expect(ingestionError(422, { detail: { code: 'invalid_request', message: 'Too many years.', hint: 'Ask for fewer.' } })).toEqual({ message: 'Too many years.', hint: 'Ask for fewer.' });
    expect(ingestionError(409, null).message).toContain('already');
    expect(ingestionError(503, null).message).toContain('switched off');
    expect(ingestionError(0, null).message).toContain('could not be reached');
  });
});

describe('summariseResult', () => {
  it('says which years are usable, partial and empty, and that empty years are not estimated', () => {
    const s = summariseResult(result([year(2021, 'observed'), year(2022, 'no_usable_data'), year(2023, 'observed'), year(2024, 'partial_coverage'), year(2025, 'observed')]));
    expect(s[0]).toBe('3 of 5 requested years have a usable value (2021, 2023, 2025).');
    expect(s.join(' ')).toContain('2024 has a value for only part of the project area');
    expect(s.join(' ')).toContain('2022 has no value. It is left empty, not estimated.');
  });
  it('counts requested years the result did not report as empty', () => {
    const s = summariseResult(result([year(2021, 'observed')], { years_requested: [2021, 2022] }));
    expect(s.join(' ')).toContain('1 of 2 requested years');
    expect(s.join(' ')).toContain('2022 has no value');
  });
  it('is empty without a result', () => {
    expect(summariseResult(null)).toEqual([]);
  });
});

describe('ObservationIngestionPanel rendering', () => {
  it('empty list: explanation, form and an empty message', () => {
    const m = render(list());
    expect(m).toContain('You can ask GroundTruth to read Sentinel-2 images');
    expect(m).toContain('data-testid="ingestion-empty"');
    expect(m).toContain('June (1 to 30 June)');
    // A preset names its dates only; it must not describe one region's seasons (found in the user audit).
    expect(m).not.toContain('southern Africa)');
    expect(m).toContain('fewer usable scenes');
    expect(m).toContain('NDMI (moisture)');
    expect(m).toContain('Advanced options');
    expect(m).toContain('Request satellite data');
  });
  it('queued with a waiting hint: shows elapsed time, the hint verbatim and a cancel button, and disables new requests', () => {
    const m = render(list({ active: true, ingestions: [ing({ status: 'queued', age_seconds: 420, waiting_hint: 'No worker has picked this up yet. Ask your administrator to start the worker.' })] }));
    expect(m).toContain('Waiting');
    expect(m).toContain('7 min ago');
    expect(m).toContain('No worker has picked this up yet. Ask your administrator to start the worker.');
    expect(m).toContain('Cancel request');
    expect(m).toContain('No satellite data has been read yet');
    expect(m).not.toMatch(/Details/);
  });
  it('running: no cancel button, no details', () => {
    const m = render(list({ active: true, ingestions: [ing({ status: 'running', started_at: '2026-11-09T10:01:00Z' })] }));
    expect(m).toContain('Running');
    expect(m).not.toContain('Cancel request');
    expect(m).toContain('Nothing is stored until it finishes');
  });
  it('succeeded: per-year table, coverage, limitations and provenance, all from the API', () => {
    const years = [2021, 2022, 2023, 2024, 2025].map((y) => year(y, 'observed'));
    const m = render(list({ ingestions: [ing({ status: 'succeeded', finished_at: '2026-11-09T10:05:00Z', ledger_record_id: 'AUDIT-123', result: result(years, { years_requested: [2021, 2022, 2023, 2024, 2025] }) })] }));
    expect(m).toContain('Finished');
    expect(m).toContain('5 of 5 requested years have a usable value');
    expect(m).toContain('0.457');
    expect(m).toContain('35KQV');
    expect(m).toContain('2022-06-04');
    expect(m).toContain('sentinel-2-l2a');
    expect(m).toContain('v1.2.3');
    expect(m).toContain('median composite');
    expect(m).toContain('ndvi_p1.json');
    expect(m).toContain('abcdef01');
    expect(m).not.toContain('abcdef0123456789abcdef');
    expect(m).toContain('AUDIT-123');
    expect(m).toContain('Cloud cover can hide the ground.');
    expect(m).toContain('do not measure tree survival, carbon or biodiversity');
    expect(m).toContain('does not show that the project caused it');
    expect(m).not.toContain('Cancel request');
  });
  it('partial: says INCOMPLETE and lists the empty and partly covered years', () => {
    const years = [year(2021, 'observed'), year(2022, 'no_usable_data'), year(2023, 'partial_coverage')];
    const m = render(list({ ingestions: [ing({ status: 'partial', status_detail: 'Two years had no clear scenes.', result: result(years, { years_requested: [2021, 2022, 2023] }) })] }));
    expect(m).toContain('INCOMPLETE');
    expect(m).toContain('Two years had no clear scenes.');
    expect(m).toContain('data-year-state="no_usable_data"');
    expect(m).toContain('No value (left empty)');
    expect(m).toContain('Part of the area only');
    expect(m).toContain('2022 has no value. It is left empty, not estimated.');
    expect(m).toContain('61.5%');
    expect(m).not.toMatch(/ingested/i);
  });
  it('failed: shows the server detail and error code, nothing about stored values', () => {
    const m = render(list({ ingestions: [ing({ status: 'failed', status_detail: 'The image catalog did not answer.', error_code: 'catalog_unavailable' })] }));
    expect(m).toContain('Failed');
    expect(m).toContain('The image catalog did not answer. (Error code: catalog_unavailable.)');
    expect(m).toContain('no new satellite values were stored');
    expect(m).toContain('This request has no result to show.');
  });
  it('cancelled: no details', () => {
    const m = render(list({ ingestions: [ing({ status: 'cancelled' })] }));
    expect(m).toContain('Cancelled');
    expect(m).not.toContain('<summary>Details');
  });
  it('disabled: no form, shows the reason', () => {
    const m = render(list({ enabled: false, explanation: 'Satellite requests are turned off on this server.' }));
    expect(m).toContain('data-testid="ingestion-disabled"');
    expect(m).toContain('Satellite requests are turned off on this server.');
    expect(m).not.toContain('<form');
  });
  it('read-only viewer: no form and no cancel, with the plain reason', () => {
    const m = render(list({ active: true, ingestions: [ing({ status: 'queued' })] }), false, 'Your role in this organization is read-only.');
    expect(m).toContain('data-testid="ingestion-readonly"');
    expect(m).toContain('Your role in this organization is read-only.');
    expect(m).not.toContain('<form');
    expect(m).not.toContain('Cancel request');
    expect(m).toContain('Waiting');
  });
});

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('observations client', () => {
  it('lists, requests and cancels with the session cookie and surfaces message and hint', async () => {
    const f = vi.fn().mockResolvedValueOnce(res(200, list())).mockResolvedValueOnce(res(202, ing())).mockResolvedValueOnce(res(422, { detail: { code: 'invalid_request', message: 'Bad season.', hint: 'Use June.' } })).mockResolvedValueOnce(res(200, ing({ status: 'cancelled' })));
    expect((await fetchIngestions('p1', f)).ok).toBe(true);
    const ok = await requestIngestion('p1', validateForm(defaultForm(limits), limits).request!, f);
    expect(ok.ok).toBe(true);
    const bad = await requestIngestion('p1', validateForm(defaultForm(limits), limits).request!, f);
    expect(bad).toMatchObject({ ok: false, status: 422, message: 'Bad season.', hint: 'Use June.' });
    expect((await cancelIngestion('p1', 'i1', f)).ok).toBe(true);
    const [url, init] = f.mock.calls[1];
    expect(String(url)).toContain('/projects/p1/observations/ingestions');
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(String(f.mock.calls[3][0])).toContain('/ingestions/i1/cancel');
  });
  it('a network failure is a quiet, plain error', async () => {
    const r = await fetchIngestions('p1', vi.fn().mockRejectedValue(new Error('down')));
    expect(r).toMatchObject({ ok: false, status: 0 });
  });
});

describe('stepper: satellite data step', () => {
  const inv = (over: Record<string, unknown> = {}) => ({ ...inventoryFull, indicators: [], items: null, documents_count: 0, climate_status: 'unavailable', observation_ingestion: { available: true, message: 'You can request satellite data.' }, ...over }) as NonNullable<LifecycleInput['inventory']>;
  const base = (over: Partial<LifecycleInput> = {}): LifecycleInput => ({
    project: { boundary_sha256: 'abc' },
    inventory: inv(),
    assessment: { level: 0, level_name: 'Not assessable' },
    claims: null,
    ledger: null,
    ...over,
  });
  const sat = (i: LifecycleInput) => lifecycleSteps(i).find((s) => s.label === 'Satellite data')!;

  it('available and nothing stored: a next step that says Request satellite data, linked to the observation tab', () => {
    const s = sat(base({ ingestions: { active: false, ingestions: [] }, inventory: inv({ documents_count: 1 }) }));
    expect(s.status).toBe('current');
    expect(s.description).toContain('Request satellite data');
    expect(s.segment).toBe('observation');
  });
  it('a queued or running request makes it in progress', () => {
    expect(sat(base({ ingestions: { active: true, ingestions: [{ status: 'queued' }] } })).status).toBe('in_progress');
    expect(sat(base({ ingestions: { ingestions: [{ status: 'running' }] } })).status).toBe('in_progress');
  });
  it('stored observations make it done even while another request runs', () => {
    expect(sat(base({ inventory: inv({ indicators: inventoryFull.indicators }), ingestions: { active: true, ingestions: [{ status: 'running' }] } })).status).toBe('done');
  });
  it('a failed or empty-partial result with nothing stored is never done', () => {
    for (const status of ['failed', 'partial', 'cancelled'] as const) {
      const s = sat(base({ ingestions: { active: false, ingestions: [{ status }] } }));
      expect(s.status).not.toBe('done');
      expect(['current', 'pending']).toContain(s.status);
    }
    expect(sat(base({ ingestions: { active: false, ingestions: [{ status: 'failed' }] } })).description).toContain('nothing is stored');
  });
  it('unavailable only when the inventory says it cannot be done, using the API message', () => {
    const s = sat(base({ inventory: inv({ observation_ingestion: { available: false, message: 'No path exists.' } }) }));
    expect(s.status).toBe('unavailable');
    expect(s.description).toBe('No path exists.');
  });
  it('ingestions that could not be read assert nothing extra', () => {
    expect(sat(base({ ingestions: null })).status).toBe('pending');
  });
});

describe('EvidenceGuidance link', () => {
  const g = (available: boolean, href?: string) =>
    renderToStaticMarkup(<EvidenceGuidance inventory={{ missing_evidence: [], next_steps: [], observation_ingestion: { available, message: 'msg' } }} observationHref={href} />);
  it('links to the Earth Observation tab when available', () => {
    const m = g(true, '/app/a/projects/p/observation');
    expect(m).toContain('href="/app/a/projects/p/observation"');
    expect(m).toContain('Request satellite data');
  });
  it('has no link when unavailable', () => {
    expect(g(false, '/app/a/projects/p/observation')).not.toContain('href=');
  });
});
