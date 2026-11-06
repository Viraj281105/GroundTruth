import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { CaseSummary } from '../src/lib/types';
import { DEFAULT_QUERY, distinct, filterCases, statusInfo } from '../src/features/cases/filter';
import { curvePoints, INTERVENTION_X, revealX, scrollProgress } from '../src/features/home/curve';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

const mk = (o: Partial<CaseSummary>): CaseSummary => ({
  case_id: 'a', name: 'Alpha', country: 'Zambia', standard: 'VCS', registry_id: null,
  ecosystem: 'forest', indicator: 'ndvi', pre_period: '2010-2014', post_period: '2015-2020',
  status: 'scaffolded', has_known_reference: false, ...o,
} as CaseSummary);

const data = [
  mk({ case_id: 'k', name: 'Kariba', standard: 'VCS', country: 'Zambia' }),
  mk({ case_id: 'm', name: 'Mikoko', standard: 'Plan Vivo', country: 'Kenya', status: 'refused', pre_period: '2005-2009' }),
  mk({ case_id: 'c', name: 'Cambodia', standard: 'VCS', country: 'Cambodia', status: 'analysed' }),
];

describe('filterCases', () => {
  it('searches across fields, case-insensitively', () => {
    expect(filterCases(data, { ...DEFAULT_QUERY, search: 'kenya' }).map((c) => c.case_id)).toEqual(['m']);
  });
  it('filters by standard and status', () => {
    expect(filterCases(data, { ...DEFAULT_QUERY, standard: 'VCS' })).toHaveLength(2);
    expect(filterCases(data, { ...DEFAULT_QUERY, status: 'refused' })).toHaveLength(1);
  });
  it('sorts by name and by baseline period', () => {
    expect(filterCases(data, DEFAULT_QUERY).map((c) => c.name)).toEqual(['Cambodia', 'Kariba', 'Mikoko']);
    expect(filterCases(data, { ...DEFAULT_QUERY, sort: 'period' })[0].name).toBe('Mikoko');
  });
  it('returns an empty list when nothing matches and derives options from data', () => {
    expect(filterCases(data, { ...DEFAULT_QUERY, search: 'zzz' })).toEqual([]);
    expect(distinct(data, 'standard')).toEqual(['Plan Vivo', 'VCS']);
  });
  it('labels known statuses and passes unknown ones through', () => {
    expect(statusInfo('refused').label).toBe('Refused');
    expect(statusInfo('weird').label).toBe('weird');
  });
});

describe('curvePoints', () => {
  it('is deterministic, identical before the intervention and diverging after', () => {
    const a = curvePoints(50);
    expect(a).toEqual(curvePoints(50));
    for (const p of a.filter((p) => p.x <= INTERVENTION_X)) expect(p.observed).toBeCloseTo(p.twin, 10);
    const last = a[a.length - 1];
    expect(last.observed - last.twin).toBeGreaterThan(0.2);
  });
  it('maps scroll to progress and reveal within bounds', () => {
    expect(scrollProgress(0, 1000, 500)).toBe(0);
    expect(scrollProgress(-250, 1000, 500)).toBe(0.5);
    expect(scrollProgress(-900, 1000, 500)).toBe(1);
    expect(revealX(-1)).toBeCloseTo(0.2);
    expect(revealX(2)).toBe(1);
  });
});

describe('CaseCard', async () => {
  const { CaseCard } = await import('../src/features/cases/CaseCard');
  it.each([['scaffolded', 'Scaffolded'], ['analysed', 'Analysed'], ['refused', 'Refused']])('renders %s', (status, label) => {
    const html = renderToStaticMarkup(<CaseCard item={mk({ status })} />);
    expect(html).toContain(label);
    expect(html).toContain('/cases/a');
    expect(html).toContain('Alpha');
  });
});
