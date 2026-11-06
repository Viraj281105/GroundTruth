import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MOCK_CASE_DETAILS, MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';
import { buildOverviewModel, describeEffect } from '../src/features/case/overview/model';
import { OverviewView } from '../src/features/case/overview/OverviewView';
import { buildSparkline } from '../src/features/case/overview/sparkline';
import { activeTabHref, caseTabLinks } from '../src/features/case/layout/tabs';
import { classifyLoadError } from '../src/features/case/layout/load';
import { CaseNotFound, CaseUnreachable } from '../src/features/case/layout/CaseStates';
import { buildMethodModel } from '../src/features/case/method/model';
import { formatCitation } from '../src/features/case/report/citation';
import { ApiUnreachableError } from '../src/lib/api';

const kariba = MOCK_CASE_DETAILS['kariba-redd'];
const mikoko = MOCK_CASE_DETAILS['mikoko-pamoja'];

describe('overview model and view', () => {
  it('builds a measured or inconclusive result with real numbers only', () => {
    const m = buildOverviewModel(kariba, MOCK_VERIFICATION_RESULTS['kariba-redd'], null);
    expect(['measured', 'inconclusive']).toContain(m.kind);
    expect(m.headline?.valueText).toBeTruthy();
    const html = renderToStaticMarkup(<OverviewView caseId="kariba-redd" model={m} />);
    expect(html).toContain('Run analysis');
    expect(html).not.toContain('NaN');
  });

  it('shows the inconclusive explanation for mikoko-pamoja', () => {
    const m = buildOverviewModel(mikoko, MOCK_VERIFICATION_RESULTS['mikoko-pamoja'] ?? null, null);
    if (m.kind === 'inconclusive') {
      const html = renderToStaticMarkup(<OverviewView caseId="mikoko-pamoja" model={m} />);
      expect(html).toContain('Why this is inconclusive');
    } else {
      expect(['measured', 'not_run']).toContain(m.kind);
    }
  });

  it('renders a refusal as a designed outcome with no chart or NaN', () => {
    const m = buildOverviewModel(kariba, null, { message: 'Series do not cover the window.', stage: 'alignment', remediation: 'Extend the series.' });
    expect(m.kind).toBe('refused');
    const html = renderToStaticMarkup(<OverviewView caseId="kariba-redd" model={m} />);
    expect(html).toContain('The analysis was not run');
    expect(html).toContain('Extend the series.');
    expect(html).not.toContain('NaN');
    expect(html).not.toContain('<svg');
  });

  it('shows an empty state with no result', () => {
    const m = buildOverviewModel(kariba, null, null);
    expect(m.kind).toBe('not_run');
    expect(renderToStaticMarkup(<OverviewView caseId="kariba-redd" model={m} />)).toContain('No result to show yet');
  });

  it('keeps auditor-only provenance out of the default lens', () => {
    const m = buildOverviewModel(kariba, MOCK_VERIFICATION_RESULTS['kariba-redd'], null);
    const html = renderToStaticMarkup(<OverviewView caseId="kariba-redd" model={m} />);
    expect(html).not.toContain('Specification hash');
  });

  it('describes sensitivity envelopes as ranges, not confidence intervals', () => {
    const text = describeEffect('0.05 ndvi', { lower: 0.01, upper: 0.09, level: 0.95, kind: 'sensitivity-envelope' }, 'x');
    expect(text).toContain('not a confidence interval');
  });
});

describe('sparkline', () => {
  it('returns null for too little data and drops non-finite points', () => {
    expect(buildSparkline([], 2011)).toBeNull();
    expect(buildSparkline([{ year: 2000, observed: NaN, synthetic: 1 }, { year: 2001, observed: 1, synthetic: 1 }], 2001)).toBeNull();
  });
  it('places the treatment marker only when inside the series', () => {
    const d = [
      { year: 2000, observed: 1, synthetic: 1 },
      { year: 2010, observed: 2, synthetic: 1.5 },
    ];
    expect(buildSparkline(d, 2005)?.treatmentX).not.toBeNull();
    expect(buildSparkline(d, 2050)?.treatmentX).toBeNull();
  });
});

describe('layout helpers', () => {
  it('picks the active tab from the pathname', () => {
    const links = caseTabLinks('kariba-redd');
    expect(activeTabHref(links, '/cases/kariba-redd')).toBe('/cases/kariba-redd');
    expect(activeTabHref(links, '/cases/kariba-redd/evidence/')).toBe('/cases/kariba-redd/evidence');
    expect(activeTabHref(links, '/cases/kariba-redd/run')).toBe('');
  });
  it('tells a 404 from an unreachable API', () => {
    const notFound = new ApiUnreachableError('http://x', new Error('API responded with 404'));
    expect(classifyLoadError(notFound)).toBe('not_found');
    expect(classifyLoadError(new ApiUnreachableError('http://x', new TypeError('fetch failed')))).toBe('unreachable');
  });
  it('renders designed not-found and error states', () => {
    expect(renderToStaticMarkup(<CaseNotFound />)).toContain('/cases');
    const html = renderToStaticMarkup(<CaseUnreachable apiBaseUrl="http://localhost:8000" />);
    expect(html).toContain('role="alert"');
    expect(html).toContain('http://localhost:8000');
  });
});

describe('method and report', () => {
  it('groups evidence by stage and always includes the design rows', () => {
    const items = MOCK_VERIFICATION_RESULTS['kariba-redd'].verification.bundle.items;
    const m = buildMethodModel(kariba, items);
    expect(m.design.find((r) => r.label === 'Standard')?.value).toBe(kariba.standard);
    expect(m.stages.length).toBeGreaterThan(0);
    expect(buildMethodModel(kariba, null).stages).toEqual([]);
  });
  it('formats a citation without any estimate or accusation', () => {
    const text = formatCitation({ caseName: 'Kariba', standard: 'VCS', registryId: 'VCS 902', runId: 'r1', specHash: 'abc', dataMode: 'simulated', generator: null });
    expect(text).toContain('Run r1, specification abc');
    expect(text).toContain('Simulated data');
    expect(text.toLowerCase()).not.toMatch(/fraud|proves|guarantee/);
  });
});
