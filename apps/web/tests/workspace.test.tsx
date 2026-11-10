import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { components } from '../src/lib/generated/schema';
import {
  apiErrorMessage,
  canCreateProject,
  dataModeLabel,
  diagnosticsAllowed,
  diagnosticsVisible,
  dossierVisible,
  isLibraryCase,
  legacyReportsAvailable,
  portfolioRedirect,
  projectDataMode,
  tabsFor,
  WORKSPACE_TABS,
} from '../src/features/projects/model';
import { ReportsView } from '../src/features/projects/ReportsView';
import { ProjectBadges } from '../src/features/projects/ProjectBadges';

// ReportsView refreshes the page after a dossier download (see tests/dossier-download.test.ts).
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

type Project = components['schemas']['ProjectView'];
type Level = Project['access_level'];
const project = (over: Partial<Project> = {}): Project => ({
  id: 'p1',
  slug: 'kariba',
  name: 'Kariba',
  country: 'ZW',
  ecosystem: 'forest',
  intervention: 'REDD+',
  treatment_start_year: 2011,
  data_mode: 'simulated',
  owner_slug: 'reference',
  owner_name: 'Reference',
  access_level: 'view',
  boundary_sha256: 'abc',
  reported_funding_amount: null,
  reported_funding_currency: null,
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});
const LEVELS: Level[] = ['owner', 'audit', 'contribute', 'view'];

describe('workspace tabs', () => {
  it('lists the same seven tabs in order at every level (tabsFor is level-independent; redaction happens inside tabs)', () => {
    for (const l of LEVELS) expect(tabsFor(l).map((t) => t.segment)).toEqual(['overview', 'observation', 'climate', 'evidence', 'verification', 'reports', 'activity']);
    expect(WORKSPACE_TABS.map((t) => t.label)).toEqual(['Overview', 'Earth Observation', 'Climate', 'Evidence', 'Verification', 'Reports', 'Activity']);
  });
  it('shows diagnostics only at owner and audit', () => {
    expect(LEVELS.map((l) => diagnosticsAllowed(l))).toEqual([true, true, false, false]);
  });
  it('diagnosticsVisible needs a bundle and owner/audit', () => {
    const bundle = { items: [] };
    expect(LEVELS.map((l) => diagnosticsVisible(bundle, l))).toEqual([true, true, false, false]);
    for (const l of LEVELS) expect(diagnosticsVisible(null, l)).toBe(false);
  });
  it('shows the dossier only at owner and audit', () => {
    expect(LEVELS.map(dossierVisible)).toEqual([true, true, false, false]);
  });
});

describe('reports tab', () => {
  const html = (level: Level, caseId: string | null) => renderToStaticMarkup(<ReportsView projectId="p1" level={level} caseId={caseId} />);
  it('hides the dossier link below audit', () => {
    expect(html('view', 'kariba-redd')).not.toMatch(/dossier/i);
    expect(html('contribute', 'kariba-redd')).not.toMatch(/dossier/i);
    expect(html('audit', 'kariba-redd')).toMatch(/dossier/i);
    expect(html('owner', 'kariba-redd')).toMatch(/dossier/i);
  });
  it('hides the monitoring report links when the project has no case_id', () => {
    expect(legacyReportsAvailable(null)).toBe(false);
    const h = html('owner', null);
    expect(h).not.toMatch(/Download PDF/);
    expect(h).not.toMatch(/Download CSV/);
    expect(h).toMatch(/dossier/i);
    expect(html('view', 'kariba-redd')).toMatch(/Download PDF/);
  });
  it('hints that the monitoring report needs a completed run', () => {
    expect(html('owner', null)).toMatch(/becomes available after a completed run/);
    expect(html('view', 'kariba-redd')).not.toMatch(/becomes available/);
  });
  it('says so when nothing is downloadable', () => {
    expect(html('view', null)).toMatch(/No reports are available/);
  });
});

describe('library case vs simulated banner', () => {
  it('treats a boundary-less project as a library case, never synthetic output', () => {
    const lib = project({ boundary_sha256: null, data_mode: 'simulated' });
    expect(isLibraryCase(lib)).toBe(true);
    expect(projectDataMode(lib)).toBe('observed');
    expect(dataModeLabel(lib)).toBe('library case — no boundary or data');
    expect(renderToStaticMarkup(<ProjectBadges project={lib} />)).toMatch(/library case — no boundary or data/);
    expect(renderToStaticMarkup(<ProjectBadges project={lib} />)).not.toMatch(/Simulated/i);
  });
  it('raises simulated for a simulated project with a boundary', () => {
    const sim = project();
    expect(isLibraryCase(sim)).toBe(false);
    expect(projectDataMode(sim)).toBe('simulated');
    expect(dataModeLabel(sim)).toMatch(/Simulated/);
    expect(renderToStaticMarkup(<ProjectBadges project={sim} />)).toMatch(/Access: view/);
  });
  it('labels observed projects', () => {
    expect(projectDataMode(project({ data_mode: 'observed' }))).toBe('observed');
    expect(dataModeLabel(project({ data_mode: 'observed' }))).toBe('Real project (not simulated)');
  });
});

describe('guards and error mapping', () => {
  it('portfolio redirects every org type except funder and government', () => {
    expect(portfolioRedirect('demo', 'funder')).toBeNull();
    expect(portfolioRedirect('demo', 'government')).toBeNull();
    for (const t of ['ngo', 'auditor', 'reference'] as const) expect(portfolioRedirect('demo', t)).toBe('/app/demo/dashboard');
  });
  it('only non-viewer members of non-reference orgs can create projects', () => {
    expect(canCreateProject('ngo', 'member')).toBe(true);
    expect(canCreateProject('ngo', 'viewer')).toBe(false);
    expect(canCreateProject('reference', 'owner')).toBe(false);
  });
  it('maps 404, 403 and 422 to distinct messages and surfaces server detail', () => {
    expect(apiErrorMessage(404)).toMatch(/not found|no access/i);
    expect(apiErrorMessage(403)).toMatch(/not allow|permission/i);
    expect(apiErrorMessage(422, 'Boundary must be a Polygon')).toBe('Boundary must be a Polygon');
    expect(apiErrorMessage(409, 'Already a member')).toBe('Already a member');
    expect(apiErrorMessage(413)).toMatch(/5 MB/);
    expect(apiErrorMessage(500)).toMatch(/server/i);
    expect(apiErrorMessage(0)).toMatch(/reach/i);
  });
});
