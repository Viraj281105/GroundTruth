import type { BarItem, LineSeries, Tone } from '../../../components/charts';
import type { ChartDataPoint, VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import { findEvidence, numberQualifier, numberValue } from '../../../lib/evidence';
import { formatEvidenceValue } from '../../../lib/formatters';
import type { Evidence } from '../../../lib/types';

/**
 * Pure data preparation for the chart figures. Every function returns null (or an
 * empty list) when the API/fixture did not provide the numbers: nothing is invented.
 */

export interface RangeFigure {
  estimate: number;
  low: number;
  high: number;
  /** Unit suffix with a leading space, or empty. */
  unit: string;
  kind: string;
}

export function effectRange(items: Evidence[] | undefined): RangeFigure | null {
  const e = findEvidence(items, 'effect.point_estimate');
  const estimate = numberValue(e);
  const ci = e?.confidence;
  if (estimate === undefined || !ci) return null;
  if (![ci.lower, ci.upper].every(Number.isFinite)) return null;
  return { estimate, low: ci.lower, high: ci.upper, unit: e?.unit ? ` ${e.unit}` : '', kind: ci.kind };
}

export interface DonutFigure {
  value: number;
  max: number;
  tone: Tone;
  caption: string;
}

/** Pre-period error against the gate threshold; needs both numbers from the bundle. */
export function fitFigure(items: Evidence[] | undefined): DonutFigure | null {
  const e = findEvidence(items, 'fit.relative_pre_rmspe');
  const value = numberValue(e);
  const gate = numberQualifier(e, 'gate_threshold');
  if (value === undefined || gate === undefined || gate <= 0) return null;
  return { value, max: gate, tone: value <= gate ? 'accent' : 'caution', caption: `Pre-period error, gate ${gate}` };
}

export interface PlaceboFigure extends DonutFigure {
  rank: number | null;
  total: number | null;
}

/** The permutation p-value as a share of 1, with the rank when the bundle returned it. */
export function placeboFigure(items: Evidence[] | undefined): PlaceboFigure | null {
  const e = findEvidence(items, 'placebo.p_value');
  const value = numberValue(e);
  if (value === undefined) return null;
  const rank = numberQualifier(e, 'rank') ?? null;
  const total = numberValue(findEvidence(items, 'placebo.n_units')) ?? null;
  const rankText = rank !== null && total !== null ? `rank ${rank} of ${total}` : 'p-value';
  return { value, max: 1, tone: 'neutral', caption: `Placebo ${rankText}`, rank, total };
}

/** Top donor weights from `fit.donor_weight.*` evidence, largest first. */
export function donorWeightBars(items: Evidence[] | undefined, limit = 8): BarItem[] {
  const bars: BarItem[] = [];
  for (const e of items ?? []) {
    if (!e.id.startsWith('fit.donor_weight.')) continue;
    const w = typeof e.value === 'number' && Number.isFinite(e.value) ? e.value : null;
    if (w === null) continue;
    const q = e.qualifiers?.donor_unit_id;
    bars.push({ label: typeof q === 'string' ? q : e.id.slice('fit.donor_weight.'.length), value: w, tone: 'accent', display: `${(w * 100).toFixed(1)}%` });
  }
  return bars.sort((a, b) => b.value - a.value).slice(0, limit);
}

export interface LineFigure {
  series: LineSeries[];
  refX?: number;
}

export function lineFigure(data: readonly ChartDataPoint[], treatmentYear: number | undefined): LineFigure | null {
  const pts = data.filter((d) => [d.year, d.observed, d.synthetic].every(Number.isFinite));
  if (pts.length < 2) return null;
  return {
    series: [
      { name: 'Observed', tone: 'observed', points: pts.map((p) => ({ x: p.year, y: p.observed })) },
      { name: 'Counterfactual (synthetic)', tone: 'synthetic', dashed: true, points: pts.map((p) => ({ x: p.year, y: p.synthetic })) },
    ],
    refX: treatmentYear !== undefined && treatmentYear >= pts[0].year && treatmentYear <= pts[pts.length - 1].year ? treatmentYear : undefined,
  };
}

export type TimelineItem = VerificationFixtureData['timeline'][number];

/** Key years in order. Fixture-provided only; the list is empty when none was returned. */
export function keyTimeline(timeline: readonly TimelineItem[] | undefined, limit = 7): TimelineItem[] {
  return [...(timeline ?? [])].filter((t) => Number.isFinite(t.year)).sort((a, b) => a.year - b.year).slice(0, limit);
}

export interface EvidenceRow {
  id: string;
  label: string;
  value: string;
  stage: string;
  method: string;
}

export function evidenceRows(items: Evidence[] | undefined): EvidenceRow[] {
  return (items ?? []).map((e) => ({
    id: e.id,
    label: e.label,
    value: formatEvidenceValue(e.value, e.unit || null),
    stage: e.provenance.stage,
    method: e.provenance.method,
  }));
}

export interface OverviewFigures {
  range: RangeFigure | null;
  fit: DonutFigure | null;
  placebo: PlaceboFigure | null;
  donors: BarItem[];
  line: LineFigure | null;
  timeline: TimelineItem[];
  rows: EvidenceRow[];
}

export const NO_FIGURES: OverviewFigures = { range: null, fit: null, placebo: null, donors: [], line: null, timeline: [], rows: [] };

/** All figures for a completed run; each is null/empty when its inputs were not returned. */
export function buildFigures(fixture: VerificationFixtureData, treatmentYear: number | undefined): OverviewFigures {
  const items = fixture.verification.bundle.items;
  return {
    range: effectRange(items),
    fit: fitFigure(items),
    placebo: placeboFigure(items),
    donors: donorWeightBars(items),
    line: lineFigure(fixture.chartSeries, treatmentYear),
    timeline: keyTimeline(fixture.timeline),
    rows: evidenceRows(items),
  };
}
