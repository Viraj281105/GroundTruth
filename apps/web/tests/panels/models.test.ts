import { describe, expect, it } from 'vitest';
import { seriesPoints } from '../../src/components/panels/series.model';
import { climateAnnual } from '../../src/components/panels/climate.model';
import { portfolioRows } from '../../src/components/panels/portfolio.model';
import { inventoryRows } from '../../src/components/panels/inventory.model';
import { dimensionView } from '../../src/components/panels/dimension.model';
import { recommendationsFor } from '../../src/components/panels/recommendations.model';
import { readinessItems } from '../../src/components/panels/readiness.model';
import { levelLadder } from '../../src/components/panels/level.model';
import { activityRows } from '../../src/components/panels/activity.model';
import { karibaAssessment, observations, climate, portfolio, inventoryFull, inventoryView, activity } from './fixtures';

describe('seriesPoints', () => {
  it('keeps provenance per point, drops NaN/unavailable points and reports the gap years', () => {
    const { points, gaps } = seriesPoints(observations);
    expect(points.map((p) => p.year)).toEqual([2020, 2023]);
    expect(points[0]).toMatchObject({ evidenceState: 'DERIVED', sensor: 'Sentinel-2', nScenes: 12, aoiCoveragePct: 62.5, sceneIds: ['S2A_1', 'S2A_2'] });
    expect(gaps).toEqual([2021, 2022]);
  });
  it('treats scene ids as absent when redacted and never interpolates', () => {
    const { points } = seriesPoints(observations);
    expect(points[1].sceneIds).toBeNull();
    expect(points).toHaveLength(2);
  });
  it('returns nothing for an unavailable series', () => {
    expect(seriesPoints({ ...observations, status: 'unavailable', points: [] })).toEqual({ points: [], gaps: [] });
  });
});

describe('climateAnnual', () => {
  it('lists the real missing months sorted', () => {
    expect(climateAnnual(climate).missingMonths).toEqual(['2022-07', '2023-12']);
  });
  it('flags drought/wet from SPI-12, keeps null rainfall null and labels years outside the window as context', () => {
    const { rows } = climateAnnual(climate, { from: 2021, to: 2023 });
    const by = Object.fromEntries(rows.map((r) => [r.year, r]));
    expect(by[2019]).toMatchObject({ flag: 'drought', context: true });
    expect(by[2023]).toMatchObject({ flag: 'wet', context: false });
    expect(by[2022].rainfallMm).toBeNull();
    expect(by[2022].flag).toBe('none');
    // SPI <= -1 but served class near_normal: no flag is derived
    expect(climateAnnual(climate).rows.find((r) => r.year === 2024)).toMatchObject({ spi12: -1.2, flag: 'none' });
  });
});

describe('portfolioRows', () => {
  const p = portfolioRows(portfolio);
  it('shows funding only with a reported_by label', () => {
    expect(p.real[0].funding).toEqual({ text: '1,000 USD', reportedBy: 'Alpha Trust' });
    expect(p.real[1].funding).toBeNull();
    expect(p.simulated[0].funding).toBeNull();
  });
  it('splits simulated projects and never mixes them', () => {
    expect(p.real.map((r) => r.name)).toEqual(['Alpha', 'Beta', 'Broken']);
    expect(p.simulated.map((r) => r.name)).toEqual(['Kariba']);
    expect(p.simulated[0].simulated).toBe(true);
    expect(Object.keys(p).sort()).toEqual(['real', 'simulated']);
  });
  it('marks degraded rows as assessment unavailable', () => {
    const broken = p.real[2];
    expect(broken.degraded).toBe(true);
    expect(broken.degradedLabel).toMatch(/assessment unavailable/i);
    expect(broken.verdict).toBeNull();
  });
});

describe('inventoryRows', () => {
  it('hides checksum and scene-id columns for view', () => {
    const v = inventoryRows(inventoryView, 'view');
    expect(v.showChecksum).toBe(false);
    expect(v.showSceneIds).toBe(false);
    expect(v.items).toEqual([]);
    expect(v.boundarySha256).toBeNull();
    expect(v.summary[0]).toMatchObject({ indicator: 'ndvi', nRecords: 3 });
  });
  it('shows them when the payload carries them at a higher level', () => {
    const a = inventoryRows(inventoryFull, 'audit');
    expect(a.showChecksum).toBe(true);
    expect(a.showSceneIds).toBe(true);
    expect(a.items[0]).toMatchObject({ year: 2021, sceneIds: ['S2A_1'], scenesSha256: 'cafe01' });
    expect(a.boundarySha256).toBe('deadbeef');
  });
  it('hides checksums for view even if a payload leaked them', () => {
    expect(inventoryRows(inventoryFull, 'view').showChecksum).toBe(false);
  });
});

describe('dimensionView', () => {
  it('never gives Insufficient evidence a success/improving treatment', () => {
    const v = dimensionView({ status: 'Insufficient evidence', status_kind: 'trend_status' });
    expect(v.tone).toBe('insufficient');
    expect(v.icon).not.toBe(dimensionView({ status: 'Improving', status_kind: 'trend_status' }).icon);
  });
  it.each(['No clear change', 'Stable', 'Insufficient evidence'])('%s is not positive', (status) => {
    expect(dimensionView({ status, status_kind: 'trend_status' }).tone).not.toBe('positive');
  });
  it('decides rendering by status_kind', () => {
    expect(dimensionView({ status: 'Improving', status_kind: 'trend_status' })).toMatchObject({ kind: 'trend', tone: 'positive' });
    expect(dimensionView({ status: 'Low', status_kind: 'quality_rating' })).toMatchObject({ kind: 'quality', label: 'Low' });
    expect(dimensionView({ status: 'Inconclusive', status_kind: 'attribution_verdict' })).toMatchObject({ kind: 'verdict', tone: 'insufficient' });
    expect(dimensionView({ status: 'Supported', status_kind: 'attribution_verdict' }).tone).toBe('positive');
  });
  it('falls back to a neutral treatment for an unknown status', () => {
    expect(dimensionView({ status: 'Surprising', status_kind: 'trend_status' }).tone).toBe('insufficient');
  });
});

describe('recommendationsFor', () => {
  const recs = karibaAssessment.recommendations;
  it('reorders by persona without dropping or rewriting', () => {
    const out = recommendationsFor(recs, 'auditor');
    expect(out).toHaveLength(recs.length);
    expect(out.map((r) => r.id)).toEqual(['acquire_more_observations', 'review_boundary_or_period', 'acquire_reference_series']);
    for (const r of out) expect(recs).toContain(r);
    expect(recommendationsFor(recs, 'funder')[0].id).toBe('acquire_reference_series');
  });
  it('defaults to priority order and does not mutate its input', () => {
    const copy = [...recs];
    expect(recommendationsFor(recs, null).map((r) => r.priority)).toEqual([1, 2, 3]);
    expect(recs).toEqual(copy);
  });
});

describe('readinessItems / levelLadder / activityRows', () => {
  it('maps criteria to states and formats missing values', () => {
    const items = readinessItems({
      attribution_ready: false,
      criteria: [
        { id: 'a', name: 'A', status: 'met', observed_value: 3, required: 3, evidence_needed: '' },
        { id: 'b', name: 'B', status: 'unavailable', observed_value: null, required: undefined, evidence_needed: 'Need B' },
      ],
    });
    expect(items.map((i) => i.state)).toEqual(['met', 'unavailable']);
    expect(items[1]).toMatchObject({ observed: '-', required: '-', evidenceNeeded: 'Need B' });
  });
  it('builds a six-step ladder with the API level name', () => {
    const l = levelLadder(2, 'Contextual intelligence (simulated)');
    expect(l.badge).toBe('Level 2 · Contextual intelligence (simulated)');
    expect(l.steps).toHaveLength(6);
    expect(l.steps.map((s) => s.state)).toEqual(['reached', 'reached', 'current', 'missing', 'missing', 'missing']);
    expect(l.steps[2].name).toBe('Contextual intelligence (simulated)');
  });
  it('classifies activity kinds', () => {
    expect(activityRows(activity).map((r) => r.kind)).toEqual(['run', 'export']);
  });
});
