import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { dashboardFor } from '../src/features/dashboards/dashboardFor';
import { NgoDashboard } from '../src/features/dashboards/NgoDashboard';
import { FunderDashboard } from '../src/features/dashboards/FunderDashboard';
import { AuditorDashboard } from '../src/features/dashboards/AuditorDashboard';
import { GovernmentDashboard } from '../src/features/dashboards/GovernmentDashboard';
import { loadDashboardData } from '../src/features/dashboards/loadDashboardData';
import { climateHeadline, dataModeFor, mappableProjects, needsAttention, pickProject } from '../src/features/dashboards/derive';
import { settleBoundaries } from '../src/components/map/geo';
import type { components } from '../src/lib/generated/schema';
import { activity, climate, inventoryFull, karibaAssessment, observations, portfolio } from './panels/fixtures';

type S = components['schemas'];
const html = (el: React.ReactElement) => renderToStaticMarkup(el);
/** The `mode` prop of the SetDataMode element every dashboard renders first. */
const modeProp = (el: unknown): string => {
  const root = el as React.ReactElement<{ children: React.ReactNode }>;
  return (React.Children.toArray(root.props.children)[0] as React.ReactElement<{ mode: string }>).props.mode;
};

const proj = (slug: string, over: Partial<S['ProjectView']> = {}): S['ProjectView'] => ({
  id: `id-${slug}`,
  slug,
  name: slug.toUpperCase(),
  country: 'ZW',
  ecosystem: 'woodland',
  intervention: 'restoration',
  treatment_start_year: 2020,
  data_mode: 'observed',
  owner_slug: 'org',
  owner_name: 'Org',
  access_level: 'contribute',
  boundary_sha256: 'abc',
  reported_funding_amount: null,
  reported_funding_currency: null,
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

const real = proj('real');
const sim = proj('kariba', { data_mode: 'simulated' });
const library = proj('library', { data_mode: 'simulated', boundary_sha256: null });

const level0: S['AssessmentView'] = {
  ...karibaAssessment,
  data_mode: 'observed',
  level: 0,
  level_name: 'Not assessable',
  recommendations: [],
};
const readiness: S['ReadinessView'] = { attribution_ready: false, criteria: [], data_mode: 'simulated', access_level: 'contribute' };
const verification: S['VerificationView'] = {
  data_mode: 'simulated',
  access_level: 'audit',
  status: 'completed',
  readiness: { attribution_ready: false, criteria: [] },
  warnings: [],
  is_simulated: true,
  run_id: null,
  case_id: null,
  verdict_label: null,
  verdict_rationale: null,
  caveats: [],
  engine_version: null,
  created_at: null,
  spec_hash: null,
} as unknown as S['VerificationView'];

type Routes = Record<string, unknown>;
/** A client double keyed by path (+ `?indicator=`); a value of `Error` makes that call throw, `null` returns a 500. */
function fakeClient(routes: Routes) {
  const calls: string[] = [];
  const GET = async (path: string, init?: { params?: { query?: { indicator?: string } } }) => {
    const key = init?.params?.query?.indicator ? `${path}?${init.params.query.indicator}` : path;
    calls.push(key);
    const v = routes[key] ?? routes[path];
    if (v instanceof Error) throw v;
    if (v === undefined || v === null) return { data: undefined, response: { status: 500 } as Response };
    return { data: v, response: { status: 200 } as Response };
  };
  return { client: { GET } as unknown as Parameters<typeof loadDashboardData>[3], calls };
}

const ngoRoutes = (over: Routes = {}): Routes => ({
  '/orgs/{slug}/projects': [real, sim],
  '/orgs/{slug}/activity': activity,
  '/projects/{project_id}/assessment': karibaAssessment,
  '/projects/{project_id}/readiness': readiness,
  '/projects/{project_id}/climate': climate,
  '/projects/{project_id}/observations': observations,
  ...over,
});

describe('pickProject', () => {
  it('defaults to an observed project with a boundary, never a simulated one listed before it', () => {
    const list = [proj('a-sim', { data_mode: 'simulated' }), proj('b-lib', { boundary_sha256: null }), proj('c-real')];
    expect(pickProject(list)?.slug).toBe('c-real');
    expect(pickProject(list, 'a-sim')?.slug).toBe('a-sim');
    expect(pickProject([proj('a-sim', { data_mode: 'simulated' })])?.slug).toBe('a-sim');
  });
});

describe('dashboardFor', () => {
  it('maps each org type to its dashboard; reference uses the NGO layout', () => {
    expect(dashboardFor('ngo')).toBe(NgoDashboard);
    expect(dashboardFor('funder')).toBe(FunderDashboard);
    expect(dashboardFor('auditor')).toBe(AuditorDashboard);
    expect(dashboardFor('government')).toBe(GovernmentDashboard);
    expect(dashboardFor('reference')).toBe(NgoDashboard);
  });
});

describe('NGO dashboard', () => {
  it('renders the assessment lead, map, series, climate, readiness, activity and the two later-release panels', async () => {
    const { client } = fakeClient(ngoRoutes());
    const data = await loadDashboardData('org', 'ngo', {}, client);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('Where should we intervene or inspect?');
    for (const id of ['assessment', 'map', 'index-series', 'climate', 'readiness', 'field-tasks', 'risk-alerts', 'activity']) expect(m).toContain(`data-panel="${id}"`);
    expect(m).toContain('Available in a later release: requires the field-operations module');
    expect(m).toContain('Available in a later release: requires the risk-intelligence module');
    expect((m.match(/data-ladder-step=/g) ?? []).length).toBe(6);
    expect(m).toContain('data-read-only="false"');
  });

  it('is read-only for a reference org', async () => {
    const { client } = fakeClient(ngoRoutes());
    const data = await loadDashboardData('ref', 'reference', {}, client);
    const Dash = dashboardFor('reference');
    const m = html(<Dash data={data} />);
    expect(m).toContain('data-read-only="true"');
    expect(m).toContain('read-only');
  });

  it('shows an empty state linking to project creation when there are zero projects', async () => {
    const { client } = fakeClient(ngoRoutes({ '/orgs/{slug}/projects': [] }));
    const data = await loadDashboardData('org', 'ngo', {}, client);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('No projects yet');
    expect(m).toContain('/app/org/projects/new');
    expect(m).not.toContain('data-panel="assessment"');
  });

  it('honours ?project=<slug> and offers a switcher', async () => {
    const { client, calls } = fakeClient(ngoRoutes());
    const data = await loadDashboardData('org', 'ngo', { project: 'kariba' }, client);
    expect(data.kind === 'ngo' && data.scope?.selected?.slug).toBe('kariba');
    expect(calls.length).toBeGreaterThan(0);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('/app/org/dashboard?project=real');
  });

  it('a failing endpoint degrades only its own panel', async () => {
    const { client } = fakeClient(ngoRoutes({ '/projects/{project_id}/climate': new Error('boom'), '/projects/{project_id}/readiness': null }));
    const data = await loadDashboardData('org', 'ngo', {}, client);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('Climate (unavailable)');
    expect(m).toContain('Readiness (unavailable)');
    expect(m).toContain('data-ladder-step'); // assessment still rendered
    expect(m).toContain('data-panel="activity"');
    expect(m).toContain('Climate could not be loaded (the API could not be reached).');
    expect(m).toContain('Readiness could not be loaded (API status 500).');
    expect(m).toContain('Vegetation index series');
  });

  it('a simulated project sets the data mode; a library case does not and is labelled', async () => {
    expect(dataModeFor([sim])).toBe('simulated');
    expect(dataModeFor([library])).toBe('observed');
    const { client, calls } = fakeClient(ngoRoutes({ '/orgs/{slug}/projects': [library] }));
    const data = await loadDashboardData('org', 'ngo', {}, client);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('Library case — no boundary or data');
    expect(m).not.toContain('data-panel="map"');
    expect(calls.some((c) => c.startsWith('/projects/'))).toBe(false);
    expect(modeProp(NgoDashboard({ data }))).toBe('observed');
  });

  it('handles a Level-0 assessment without crashing', async () => {
    const { client } = fakeClient(ngoRoutes({ '/projects/{project_id}/assessment': level0 }));
    const m = html(<NgoDashboard data={await loadDashboardData('org', 'ngo', {}, client)} />);
    expect(m).toContain('Not assessable');
  });
});

describe('Funder dashboard', () => {
  const routes: Routes = { '/orgs/{slug}/portfolio': portfolio, '/orgs/{slug}/activity': activity };

  it('leads with the portfolio, a needs-attention list and activity; fetches nothing project-level', async () => {
    const { client, calls } = fakeClient(routes);
    const data = await loadDashboardData('fund', 'funder', {}, client);
    const m = html(<FunderDashboard data={data} />);
    expect(m).toContain('Which projects show measurable progress or need investigation?');
    for (const id of ['portfolio', 'needs-attention', 'activity']) expect(m).toContain(`data-panel="${id}"`);
    expect(calls.every((c) => c.startsWith('/orgs/'))).toBe(true);
    expect(m).toContain('Assessment unavailable: assessment failed');
    expect(m).not.toMatch(/fraud|misconduct|guilty/i);
  });

  it('derives needs-attention only from real fields, excluding simulated rows', () => {
    const items = needsAttention([...portfolio.projects, ...portfolio.simulated]);
    expect(items.map((i) => i.name).sort()).toEqual(['Alpha', 'Beta', 'Broken']);
    const none = needsAttention([{ ...portfolio.projects[0]!, top_recommendation: null, assessment_level: 3, attribution_verdict: 'Supported' }]);
    expect(none).toEqual([]);
    const inconclusive = needsAttention([{ ...portfolio.projects[0]!, top_recommendation: null, assessment_level: 3, attribution_verdict: null }]);
    expect(inconclusive[0]?.reasons[0]).toBe('No attribution result is reported for this project.');
  });

  it('keeps simulated rows out of needs-attention and sets simulated mode', async () => {
    const data = await loadDashboardData('fund', 'funder', {}, fakeClient(routes).client);
    expect(html(<FunderDashboard data={data} />)).toContain('Simulated projects');
    expect(needsAttention(portfolio.simulated)).toEqual([]);
    // the panel fixture's simulated row has no boundary (a library case), so it must NOT raise the banner
    expect(modeProp(FunderDashboard({ data }))).toBe('observed');
    const bounded = { projects: portfolio.projects, simulated: [{ ...portfolio.simulated[0]!, project: { ...portfolio.simulated[0]!.project, boundary_sha256: 'abc' } }] };
    const d2 = await loadDashboardData('fund', 'funder', {}, fakeClient({ ...routes, '/orgs/{slug}/portfolio': bounded }).client);
    expect(modeProp(FunderDashboard({ data: d2 }))).toBe('simulated');
    expect(dataModeFor(portfolio.projects.map((r) => r.project))).toBe('observed');
  });

  it('pins the needs-attention copy exactly', () => {
    const base = portfolio.projects[0]!;
    expect(needsAttention([{ ...base, top_recommendation: null, assessment_level: 1, level_name: 'Basic monitoring', attribution_verdict: null }])[0]?.reasons).toEqual([
      'The reported assessment level is 1 (Basic monitoring).',
      'No attribution result is reported for this project.',
    ]);
    expect(needsAttention([{ ...base, top_recommendation: null, assessment_level: 3, attribution_verdict: 'Inconclusive' }])[0]?.reasons).toEqual([
      'Attribution is reported as inconclusive: the available evidence does not currently allow attribution to be assessed.',
    ]);
  });

  it('says no projects are shared when the portfolio is empty', async () => {
    const data = await loadDashboardData('fund', 'funder', {}, fakeClient({ '/orgs/{slug}/portfolio': { projects: [], simulated: [] }, '/orgs/{slug}/activity': [] }).client);
    const m = html(<FunderDashboard data={data} />);
    expect(m).toContain('No projects are shared with your organization yet.');
    expect(m).not.toContain('No real project currently has');
  });

  it('a failing portfolio degrades only that panel; activity survives', async () => {
    const data = await loadDashboardData('fund', 'funder', {}, fakeClient({ '/orgs/{slug}/portfolio': new Error('x'), '/orgs/{slug}/activity': activity }).client);
    const m = html(<FunderDashboard data={data} />);
    expect(m).toContain('Portfolio (unavailable)');
    expect(m).toContain('Needs attention (unavailable)');
    expect(m).toContain('data-panel="activity"');
    expect(m).toContain('Kariba');
  });
});

describe('Auditor dashboard', () => {
  const routes = (over: Routes = {}): Routes => ({
    '/orgs/{slug}/projects': [proj('real', { access_level: 'audit' })],
    '/orgs/{slug}/activity': activity,
    '/projects/{project_id}/assessment': karibaAssessment,
    '/projects/{project_id}/evidence-inventory': inventoryFull,
    '/projects/{project_id}/readiness': readiness,
    '/projects/{project_id}/verification': verification,
    '/projects/{project_id}/climate': climate,
    '/projects/{project_id}/observations': observations,
    ...over,
  });

  it('renders assessment, inventory, readiness, verdict, data quality, dossier link and activity', async () => {
    const data = await loadDashboardData('aud', 'auditor', {}, fakeClient(routes()).client);
    const m = html(<AuditorDashboard data={data} />);
    expect(m).toContain('Which claims are substantiated and what evidence is missing?');
    for (const id of ['assessment', 'evidence-inventory', 'verdict', 'readiness', 'data-quality', 'dossier', 'activity']) expect(m).toContain(`data-panel="${id}"`);
    expect(m).toContain('/projects/id-real/export/dossier');
    expect(m).toContain('Missing climate months: 2');
    expect(m).toContain('Sensors: Sentinel-2');
    expect(m).toContain('62.5% across served years');
  });

  it('hides the dossier link below audit level', async () => {
    const data = await loadDashboardData('aud', 'auditor', {}, fakeClient(routes({ '/orgs/{slug}/projects': [proj('real', { access_level: 'view' })] })).client);
    expect(html(<AuditorDashboard data={data} />)).not.toContain('export/dossier');
  });

  it('a failing inventory degrades only that panel', async () => {
    const data = await loadDashboardData('aud', 'auditor', {}, fakeClient(routes({ '/projects/{project_id}/evidence-inventory': new Error('x') })).client);
    const m = html(<AuditorDashboard data={data} />);
    expect(m).toContain('Evidence inventory (unavailable)');
    expect(m).toContain('data-panel="verdict"');
    expect(m).toContain('data-ladder-step');
  });
});

describe('Government dashboard', () => {
  const routes: Routes = {
    '/orgs/{slug}/projects': [real, sim, library, proj('other')],
    '/orgs/{slug}/portfolio': portfolio,
    '/projects/{project_id}/climate': climate,
  };

  it('shows the map, portfolio, per-project climate headline and the regional-SPI unavailable panel with no invented numbers', async () => {
    const { client, calls } = fakeClient(routes);
    const data = await loadDashboardData('gov', 'government', {}, client);
    const m = html(<GovernmentDashboard data={data} />);
    expect(m).toContain('Which landscapes need attention?');
    for (const id of ['map', 'portfolio', 'climate-headlines', 'regional-spi']) expect(m).toContain(`data-panel="${id}"`);
    expect(m).toContain('Regional district climate summaries are not served by the API yet');
    expect(m).toContain('A regional climate endpoint (later sub-project)');
    // headline: latest year with rainfall is 2024 (700 mm), served class near_normal
    expect(m).toContain('2024: 700 mm annual rainfall, drought class &quot;near_normal&quot;');
    // climate fetched only for observed projects with a boundary
    expect(calls.filter((c) => c === '/projects/{project_id}/climate')).toHaveLength(2);
    const spi = m.slice(m.indexOf('data-panel="regional-spi"'));
    const text = spi
      .replace(/<[^>]*>/g, ' ')
      .replace('Regional district climate summaries are not served by the API yet.', '')
      .replace('A regional climate endpoint (later sub-project)', '');
    expect(text).not.toMatch(/\d/);
  });

  it('climateHeadline uses the served class and skips years without rainfall', () => {
    expect(climateHeadline(climate)).toEqual({ year: 2024, annualRainfallMm: 700, drought: 'near_normal' });
    expect(climateHeadline({ ...climate, status: 'unavailable' })).toBeNull();
  });

  it('one failing climate call degrades only that project row', async () => {
    let n = 0;
    const client = {
      GET: async (path: string) => {
        if (path === '/projects/{project_id}/climate') {
          n += 1;
          if (n === 1) throw new Error('x');
          return { data: climate, response: { status: 200 } };
        }
        return { data: routes[path], response: { status: 200 } };
      },
    } as unknown as Parameters<typeof loadDashboardData>[3];
    const m = html(<GovernmentDashboard data={await loadDashboardData('gov', 'government', {}, client)} />);
    expect(m).toContain('climate (unavailable)');
    expect(m).toContain('2024: 700 mm');
    expect(m).toContain('data-panel="portfolio"');
  });

  it('excludes simulated boundaries from the map, fails soft per boundary and keeps simulated mode', async () => {
    expect(mappableProjects([real, sim, library]).map((p) => p.slug)).toEqual(['real']);
    expect(settleBoundaries([null, { type: 'Polygon' }])).toEqual({ ok: [{ type: 'Polygon' }], failed: 1 });
    const data = await loadDashboardData('gov', 'government', {}, fakeClient({ '/orgs/{slug}/projects': [real, sim], '/orgs/{slug}/portfolio': new Error('x'), '/projects/{project_id}/climate': climate }).client);
    // mode derives from the projects list, so a failed portfolio call does not hide the simulated banner
    expect(modeProp(GovernmentDashboard({ data }))).toBe('simulated');
    expect(html(<GovernmentDashboard data={data} />)).toContain('data-panel="map"');
  });
});

describe('heading hierarchy', () => {
  it('every dashboard has exactly one h1 carrying the persona question', async () => {
    const audRoutes = ngoRoutes({ '/orgs/{slug}/projects': [proj('real', { access_level: 'audit' })], '/projects/{project_id}/evidence-inventory': inventoryFull, '/projects/{project_id}/verification': verification });
    const cases: [Parameters<typeof loadDashboardData>[1], Routes, string][] = [
      ['ngo', ngoRoutes(), 'Where should we intervene or inspect?'],
      ['funder', { '/orgs/{slug}/portfolio': portfolio, '/orgs/{slug}/activity': activity }, 'Which projects show measurable progress or need investigation?'],
      ['auditor', audRoutes, 'Which claims are substantiated and what evidence is missing?'],
      ['government', { '/orgs/{slug}/projects': [real], '/orgs/{slug}/portfolio': portfolio, '/projects/{project_id}/climate': climate }, 'Which landscapes need attention?'],
    ];
    for (const [type, routes, q] of cases) {
      const Dash = dashboardFor(type);
      const m = html(<Dash data={await loadDashboardData('o', type, {}, fakeClient(routes).client)} />);
      expect((m.match(/<h1[ >]/g) ?? []).length).toBe(1);
      expect(m).toContain(`>${q}</h1>`);
    }
  });

  it('region titles are h2 and do not duplicate panel-supplied headings', async () => {
    const data = await loadDashboardData('f', 'funder', {}, fakeClient({ '/orgs/{slug}/portfolio': portfolio, '/orgs/{slug}/activity': activity }).client);
    const m = html(<FunderDashboard data={data} />);
    expect(m).toMatch(/<h2[^>]*>Needs attention<\/h2>/);
    // No VISIBLE duplicate of the panel's own heading; the screen-reader-only h2 below keeps levels contiguous.
    const dupes = [...m.matchAll(/<h2[^>]*>(?:Portfolio|Recent activity)<\/h2>/g)].map((x) => x[0]);
    expect(dupes.length).toBeGreaterThan(0);
    dupes.forEach((h) => expect(h).toContain('sr-only'));
  });

  it('a region whose panel supplies its own heading still gets a screen-reader h2 so headings never skip a level', async () => {
    const data = await loadDashboardData('f', 'funder', {}, fakeClient({ '/orgs/{slug}/portfolio': portfolio, '/orgs/{slug}/activity': activity }).client);
    const m = html(<FunderDashboard data={data} />);
    expect(m).toMatch(/<h2 class="sr-only">[^<]+<\/h2>/);
    const levels = [...m.matchAll(/<h([1-6])[ >]/g)].map((x) => Number(x[1]));
    levels.forEach((l, i) => i > 0 && expect(l - levels[i - 1]!).toBeLessThanOrEqual(1));
  });
});

describe('fix round 1 additions', () => {
  it('a zero-project reference org has no create link', async () => {
    const data = await loadDashboardData('ref', 'reference', {}, fakeClient(ngoRoutes({ '/orgs/{slug}/projects': [] })).client);
    const m = html(<NgoDashboard data={data} />);
    expect(m).toContain('No projects yet');
    expect(m).not.toContain('projects/new');
  });

  it('dossier link shows for owner and audit, not for contribute or view', async () => {
    for (const [level, shown] of [['owner', true], ['audit', true], ['contribute', false], ['view', false]] as const) {
      const routes = ngoRoutes({ '/orgs/{slug}/projects': [proj('real', { access_level: level })], '/projects/{project_id}/evidence-inventory': inventoryFull, '/projects/{project_id}/verification': verification });
      const m = html(<AuditorDashboard data={await loadDashboardData('a', 'auditor', {}, fakeClient(routes).client)} />);
      expect(m.includes('export/dossier')).toBe(shown);
    }
  });

  it('a view-level auditor sees no checksum or scene-id columns', async () => {
    const routes = ngoRoutes({ '/orgs/{slug}/projects': [proj('real', { access_level: 'view' })], '/projects/{project_id}/evidence-inventory': inventoryFull, '/projects/{project_id}/verification': verification });
    const m = html(<AuditorDashboard data={await loadDashboardData('a', 'auditor', {}, fakeClient(routes).client)} />);
    expect(m).not.toContain('cafe01');
    expect(m).not.toContain('deadbeef');
  });

  it('coverage collapses to one value when min equals max', async () => {
    const routes = ngoRoutes({ '/orgs/{slug}/projects': [proj('real', { access_level: 'audit' })], '/projects/{project_id}/evidence-inventory': inventoryFull, '/projects/{project_id}/verification': verification });
    const m = html(<AuditorDashboard data={await loadDashboardData('a', 'auditor', {}, fakeClient(routes).client)} />);
    expect(m).toContain('62.5% across served years');
    expect(m).not.toContain('62.5% to 62.5%');
  });

  it('switching project resets the data mode (simulated -> observed)', async () => {
    const modeOf = async (project: string) => modeProp(NgoDashboard({ data: await loadDashboardData('org', 'ngo', { project }, fakeClient(ngoRoutes()).client) }));
    expect(await modeOf('kariba')).toBe('simulated');
    expect(await modeOf('real')).toBe('observed');
  });
});
