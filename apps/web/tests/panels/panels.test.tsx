import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AssessmentSummary } from '../../src/components/panels/AssessmentSummary';
import { DimensionCard } from '../../src/components/panels/DimensionCard';
import { RecommendationList } from '../../src/components/panels/RecommendationList';
import { ReadinessChecklist } from '../../src/components/panels/ReadinessChecklist';
import { IndexSeriesPanel } from '../../src/components/panels/IndexSeriesPanel';
import { ClimatePanel } from '../../src/components/panels/ClimatePanel';
import { EvidenceInventoryTable } from '../../src/components/panels/EvidenceInventoryTable';
import { VerdictPanel } from '../../src/components/panels/VerdictPanel';
import { ActivityFeed } from '../../src/components/panels/ActivityFeed';
import { PortfolioTable } from '../../src/components/panels/PortfolioTable';
import type { components } from '../../src/lib/generated/schema';
import { activity, climate, dim, inventoryFull, inventoryView, karibaAssessment, observations, portfolio } from './fixtures';

type S = components['schemas'];
const html = (el: React.ReactElement) => renderToStaticMarkup(el);

describe('AssessmentSummary (Kariba-shaped fixture)', () => {
  const m = html(<AssessmentSummary data={karibaAssessment} persona="ngo" />);
  it('shows the level badge with the API name, the six-step ladder and the layered conclusions', () => {
    expect(m).toContain('Level 2 · Contextual intelligence (simulated)');
    expect((m.match(/data-ladder-step=/g) ?? []).length).toBe(6);
    expect(m).toContain('data-ladder-state="missing"');
    expect(m).toContain('Observed outcome');
    expect(m).toContain('Climate-adjusted interpretation');
    expect(m).toContain('Needs at least 8 overlapping years');
    expect(m).toContain('No donor vegetation series.');
    expect(m).toContain('Synthetic control with placebo inference.');
    expect(m).toContain('Missing data');
    expect(m).toContain('Evidence confidence');
  });
  it('renders every one of the eight dimension cards and none of the Insufficient ones as success', () => {
    expect((m.match(/data-dimension-id=/g) ?? []).length).toBe(8);
    const cards = m.split('data-dimension-id=').slice(1);
    const insufficient = cards.filter((c) => c.includes('data-dim-label="Insufficient evidence"'));
    expect(insufficient).toHaveLength(4);
    for (const c of insufficient) {
      expect(c).toContain('data-dim-tone="insufficient"');
      expect(c).not.toContain('data-status-style="improving"');
      expect(c).not.toContain('data-dim-tone="positive"');
    }
    expect(m).not.toContain('data-status-style="improving"');
  });
  it('renders the recommendations ordered for the persona', () => {
    expect(m.indexOf('Acquire more annual observations.')).toBeLessThan(m.indexOf('Review the boundary or monitoring period.'));
  });
  it('loading and empty states', () => {
    expect(html(<AssessmentSummary loading />)).toContain('aria-busy="true"');
    expect(html(<AssessmentSummary data={null} />)).toContain('No assessment');
  });
});

describe('AssessmentSummary edge cases', () => {
  const lvl0: S['AssessmentView'] = {
    ...karibaAssessment,
    data_mode: 'observed',
    simulated_banner: null,
    level: 0,
    level_name: 'Not assessable',
    observed_outcome: { summary: '', dimension_ids: [], estimable: false, reason: 'No observations stored.' },
    recommendations: [],
    dimensions: karibaAssessment.dimensions.map((d) => ({ ...d, limitation: 'missing_data', evidence_needed: `Needs ${d.id} evidence` })),
  };
  it('level 0 renders ladder, reasons and all eight cards with limitation and evidence needed', () => {
    const m = html(<AssessmentSummary data={lvl0} />);
    expect(m).toContain('Level 0 \u00b7 Not assessable');
    expect(m).toContain('No observations stored.');
    expect((m.match(/data-dimension-id=/g) ?? []).length).toBe(8);
    expect(m).toContain('Needs vegetation_trajectory evidence');
    expect(m).toContain('Missing data');
    expect(m).toContain('No recommendations triggered');
  });
  it('renders a view-level payload with redacted fields', () => {
    const { diagnostic_refs: _a, ...attr } = karibaAssessment.attribution;
    const redacted = { ...karibaAssessment, access_level: 'view', attribution: attr, dimensions: karibaAssessment.dimensions.map(({ diagnostic_refs: _d, facts: _f, ...r }) => r) } as unknown as S['AssessmentView'];
    expect(() => html(<AssessmentSummary data={redacted} />)).not.toThrow();
  });
  it('shows the simulated banner only for simulated data', () => {
    expect(html(<AssessmentSummary data={karibaAssessment} />)).toContain('data-data-mode="simulated"');
    expect(html(<AssessmentSummary data={lvl0} />)).not.toContain('data-data-mode="simulated"');
  });
  it('states explicitly when there are no dimensions', () => {
    expect(html(<AssessmentSummary data={{ ...lvl0, dimensions: [] }} />)).toContain('No dimension results available for this project');
  });
});

describe('DimensionCard', () => {
  it('shows known / suggested / cannot establish, the typed limitation, evidence needed and confidence', () => {
    const m = html(<DimensionCard dimension={karibaAssessment.dimensions[0]} />);
    expect(m).toContain('Known');
    expect(m).toContain('NDVI 2021 to 2023: 0.41 to 0.47');
    expect(m).toContain('Cannot establish');
    expect(m).toContain('Weak statistical power');
    expect(m).toContain('At least six annual periods.');
    expect(m).toContain('Confidence');
  });
  it('renders quality ratings and attribution verdicts as labelled chips, not trend chips', () => {
    const q = html(<DimensionCard dimension={karibaAssessment.dimensions[6]} />);
    const a = html(<DimensionCard dimension={karibaAssessment.dimensions[7]} />);
    expect(q).toContain('data-dim-kind="quality"');
    expect(a).toContain('data-dim-kind="verdict"');
    expect(q).not.toContain('data-status-style');
    expect(a).toContain('Inconclusive');
  });
  it('uses the StatusChip for trend statuses and omits empty lists', () => {
    const m = html(<DimensionCard dimension={dim({ id: 'x', title: 'X', status: 'Improving' })} />);
    expect(m).toContain('data-status-style="improving"');
    expect(m).not.toContain('Cannot establish');
  });
});

describe('RecommendationList', () => {
  it('states explicitly when nothing was triggered, with no filler', () => {
    const m = html(<RecommendationList recommendations={[]} />);
    expect(m).toContain('No recommendations triggered by the available evidence');
  });
  it('shows rationale and evidence refs as non-link chips', () => {
    const m = html(<RecommendationList recommendations={karibaAssessment.recommendations} persona="funder" />);
    expect(m).toContain('No donor vegetation series.');
    expect(m).toContain('dim.comparative_performance');
    expect(m).not.toContain('<a ');
    expect(m.indexOf('Acquire reference-area series.')).toBeLessThan(m.indexOf('Acquire more annual observations.'));
  });
});

describe('RecommendationList priority', () => {
  it('prints each served priority after persona reordering', () => {
    const m = html(<RecommendationList recommendations={karibaAssessment.recommendations} persona="auditor" />);
    const item = (id: string) => m.split(`data-recommendation-id="${id}"`)[1].split('</li>')[0];
    expect(item('review_boundary_or_period')).toContain('<b>3</b>');
    expect(item('acquire_more_observations')).toContain('<b>1</b>');
  });
});

describe('ReadinessChecklist', () => {
  const r: S['ReadinessView'] = {
    data_mode: 'observed',
    access_level: 'view',
    attribution_ready: false,
    criteria: [
      { id: 'a', name: 'Pre-treatment periods', status: 'not_met', observed_value: 0, required: 3, evidence_needed: 'Three pre-treatment years' },
      { id: 'b', name: 'Donor series', status: 'unavailable', observed_value: null, required: null, evidence_needed: 'Donor vegetation series' },
      { id: 'c', name: 'Boundary', status: 'met', observed_value: 'verified', required: 'verified', evidence_needed: '' },
    ],
  };
  it('lists met / not met / unavailable with evidence needed', () => {
    const m = html(<ReadinessChecklist data={r} />);
    expect(m).toContain('Not met');
    expect(m).toContain('Unavailable');
    expect(m).toContain('Met');
    expect(m).toContain('Three pre-treatment years');
    expect(m).toContain('Not ready for attribution');
  });
});

describe('IndexSeriesPanel', () => {
  it('shows gaps, evidence-state badges, AOI coverage and scene ids only where present', () => {
    const m = html(<IndexSeriesPanel series={[observations]} initialView="table" />);
    expect(m).toContain('data-evidence-state="DERIVED"');
    expect(m).toContain('2021');
    expect(m).toContain('No observation for 2021, 2022');
    expect(m).toContain('62.5');
    expect(m).toContain('S2A_1');
  });
  it('omits the scene-id column when no point carries scene ids', () => {
    const redacted = { ...observations, points: observations.points.map((p) => ({ ...p, scene_ids: null, scenes_sha256: null })) };
    expect(html(<IndexSeriesPanel series={[redacted]} initialView="table" />)).not.toContain('Scene ids');
  });
  it('offers the four index toggles and a chart/table toggle', () => {
    const m = html(<IndexSeriesPanel series={[observations]} />);
    for (const k of ['NDVI', 'EVI', 'NDMI', 'NBR']) expect(m).toContain(k);
    expect(m).toContain('data-view="chart"');
  });
  it('renders UnavailablePanel for an unavailable series', () => {
    const m = html(<IndexSeriesPanel series={[{ ...observations, status: 'unavailable', reason: 'No scenes ingested', points: [] }]} />);
    expect(m).toContain('(unavailable)');
    expect(m).toContain('No scenes ingested');
  });
});

describe('ClimatePanel', () => {
  it('lists missing months, drought flags and context-only years', () => {
    const m = html(<ClimatePanel data={climate} observedWindow={{ from: 2021, to: 2023 }} />);
    expect(m).toContain('2022-07');
    expect(m).toContain('2023-12');
    expect(m).toContain('Drought (moderate drought)');
    expect((m.match(/data-flag="drought"/g) ?? []).length).toBe(1);
    expect(m).toContain('context only');
  });
  it('renders UnavailablePanel when unavailable', () => {
    const m = html(<ClimatePanel data={{ ...climate, status: 'unavailable', reason: 'No climate bundle', years: [] }} />);
    expect(m).toContain('(unavailable)');
    expect(m).toContain('No climate bundle');
  });
});

describe('EvidenceInventoryTable', () => {
  it('hides checksum and scene-id columns for view', () => {
    const m = html(<EvidenceInventoryTable data={inventoryView} level="view" />);
    expect(m).not.toContain('Checksum');
    expect(m).not.toContain('Scene ids');
    expect(m).toContain('ndvi');
  });
  it('shows them when present', () => {
    const m = html(<EvidenceInventoryTable data={inventoryFull} level="audit" />);
    expect(m).toContain('Checksum');
    expect(m).toContain('cafe01');
    expect(m).toContain('S2A_1');
  });
  it('renders UnavailablePanel when unavailable', () => {
    expect(html(<EvidenceInventoryTable data={{ ...inventoryView, status: 'unavailable', reason: 'Nothing stored' }} level="view" />)).toContain('(unavailable)');
  });
});

describe('VerdictPanel', () => {
  const base: S['VerificationView'] = {
    data_mode: 'simulated',
    access_level: 'view',
    status: 'completed',
    readiness: { attribution_ready: true, criteria: [] },
    warnings: ['SIMULATED DATA'],
    is_simulated: true,
    run_id: 'r1',
    case_id: 'kariba-redd',
    verdict_label: 'inconclusive',
    verdict_rationale: 'Not commensurable.',
    caveats: ['Spectral indices track vegetation condition, not carbon stocks.'],
    engine_version: '1',
    created_at: null,
    spec_hash: null,
    bundle: null,
  };
  it('reuses the screening copy and carries caveats', () => {
    const m = html(<VerdictPanel data={base} />);
    expect(m).toContain('Inconclusive');
    expect(m).toContain('Not commensurable.');
    expect(m).toContain('not carbon stocks');
  });
  it('renders UnavailablePanel when not estimable', () => {
    const m = html(<VerdictPanel data={{ ...base, status: 'not_estimable', verdict_label: null }} />);
    expect(m).toContain('(unavailable)');
  });
});

describe('ActivityFeed', () => {
  it('lists items and has an empty state', () => {
    const m = html(<ActivityFeed items={activity} />);
    expect(m).toContain('run.completed');
    expect(m).toContain('export.created');
    expect(html(<ActivityFeed items={[]} />)).toContain('No recent activity');
  });
});

describe('PortfolioTable', () => {
  const m = html(<PortfolioTable data={portfolio} />);
  it('labels reported funding and shows it only with a reporter', () => {
    expect(m).toContain('reported by Alpha Trust');
    expect(m).not.toContain('reported by </');
  });
  it('a non-degraded row without dimension statuses is not called unavailable', () => {
    const r = portfolio.projects[0];
    const { dimension_statuses: _d, ...rest } = r;
    const out = html(<PortfolioTable data={{ projects: [rest as unknown as typeof r], simulated: [] }} />);
    expect(out).toContain('Not reported at this access level');
    expect(out).not.toContain('Assessment unavailable');
  });
  it('marks degraded rows and keeps simulated projects in a separate labelled section', () => {
    expect(m).toContain('Assessment unavailable');
    const realPart = m.slice(0, m.indexOf('data-section="simulated"'));
    expect(realPart).toContain('Alpha');
    expect(realPart).not.toContain('Kariba');
    expect(m).toContain('Simulated projects');
    expect(m.toLowerCase()).not.toContain('portfolio score');
  });
  it('has an empty state', () => {
    expect(html(<PortfolioTable data={{ projects: [], simulated: [] }} />)).toContain('No projects');
  });
});
