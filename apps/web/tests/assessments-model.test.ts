import { describe, expect, it } from 'vitest';
import { claimSummary, kpis, toRow } from '../src/features/assessments/model';
import type { Schemas } from '../src/lib/api-client';

const project = (over: Partial<Schemas['ProjectView']> = {}): Schemas['ProjectView'] => ({
  id: 'p1',
  slug: 'my-project',
  name: 'My Project',
  country: 'KE',
  ecosystem: 'mangrove',
  intervention: 'restoration',
  treatment_start_year: 2020,
  data_mode: 'observed',
  owner_slug: 'acme',
  owner_name: 'Acme',
  access_level: 'owner',
  boundary_sha256: 'abc',
  reported_funding_amount: null,
  reported_funding_currency: null,
  created_at: '2026-01-01T00:00:00Z',
  ...over,
});

const assessment = { level: 1, level_name: 'Basic monitoring' } as Schemas['AssessmentView'];

describe('claimSummary', () => {
  it('reads the structured-claims counts', () => {
    const s = claimSummary({ total_claims: 5, supported_count: 2, partially_supported_count: 1, contradicted_count: 1, unverified_count: 1, has_claims: true });
    expect(s).toMatchObject({ total: 5, supported: 2, partiallySupported: 1, contradicted: 1, unverified: 1, hasClaims: true });
  });
  it('is null for a non-object body, never zeros presented as data', () => {
    expect(claimSummary(null)).toBeNull();
    expect(claimSummary('x')).toBeNull();
  });
  it('treats missing or garbage counts as 0 and has_claims from the total', () => {
    expect(claimSummary({ total_claims: 'many' })).toMatchObject({ total: 0, hasClaims: false });
  });
  it('flags a synthetic body as demo', () => {
    expect(claimSummary({ data_mode: 'synthetic', total_claims: 3 })?.isDemo).toBe(true);
  });
});

describe('assessment rows and KPIs', () => {
  it('builds the level text from the API and uses the real slug', () => {
    const row = toRow(project(), { data: assessment, status: 200 }, { data: { total_claims: 0, has_claims: false }, status: 200 });
    expect(row.level).toBe('Level 1 · Basic monitoring');
    expect(row.slug).toBe('my-project');
    expect(row.claims?.hasClaims).toBe(false);
  });
  it('an unreadable assessment or claims response is stated, not defaulted', () => {
    const row = toRow(project(), { data: null, status: 500 }, { data: null, status: 0 });
    expect(row.level).toBeNull();
    expect(row.levelUnavailable).toContain('500');
    expect(row.claims).toBeNull();
    expect(row.claimsUnavailable).toContain('no response');
  });
  it('an empty organization has all-zero KPIs', () => {
    expect(kpis([])).toEqual({ projects: 0, assessmentsAvailable: 0, simulatedProjects: 0, libraryCases: 0, claimsOnRealProjects: 0 });
  });
  it('claims from simulated projects are not counted as real', () => {
    const real = toRow(project(), { data: assessment, status: 200 }, { data: { total_claims: 4, has_claims: true }, status: 200 });
    const sim = toRow(project({ id: 'p2', data_mode: 'simulated' }), { data: assessment, status: 200 }, { data: { total_claims: 24, has_claims: true }, status: 200 });
    const k = kpis([real, sim]);
    expect(k.claimsOnRealProjects).toBe(4);
    expect(k.simulatedProjects).toBe(1);
    expect(k.projects).toBe(2);
  });
  it('a project with no boundary is a library case', () => {
    expect(toRow(project({ boundary_sha256: null }), { data: null, status: 404 }, { data: null, status: 404 }).libraryCase).toBe(true);
  });
});
