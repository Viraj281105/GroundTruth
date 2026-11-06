import type { BarItem, LineSeries } from '../../../components/charts';
import type { PreBin } from '../../../components/charts/BinnedHistogram';
import type { SignedBar } from '../../../components/charts/SignedBars';
import type { SpecDot } from '../../../components/charts/SpecDots';
import { findEvidence, numberQualifier, numberValue, sig, withUnit } from '../../../lib/evidence';
import type { ChartDataPoint, PlaceboDistributionData } from '../../../lib/fixtures/simulated-data';
import type { SpecCurve } from '../../../lib/spec-curve';
import type { Evidence } from '../../../lib/types';
import { deriveDonorWeights } from '../playground/playground-model';

/**
 * Pure data preparation for the evidence and robustness charts. Every value
 * returned was served by the API or demo fixture; when an input is missing the
 * function returns null or an empty list so the view can say "not available".
 */

/** Largest reported donor weights as percentage bars. Empty when weights were not reported. */
export function donorBars(items: Evidence[], n = 8): BarItem[] {
  return deriveDonorWeights(items)
    .slice(0, n)
    .map((d) => ({ label: d.id, value: d.weight * 100, display: `${sig(d.weight * 100)}%` }));
}

/** The gap (observed minus counterfactual) as returned per period. */
export function gapSeries(series: ChartDataPoint[]): LineSeries[] {
  const points = series.filter((p) => Number.isFinite(p.gap)).map((p) => ({ x: p.year, y: p.gap }));
  return points.length < 2 ? [] : [{ name: 'Gap (observed minus counterfactual)', tone: 'accent', points }];
}

export function placeboBins(p: PlaceboDistributionData): PreBin[] {
  return p.bins.map((b) => ({ from: b.min, to: b.max, count: b.count }));
}

export interface FitDonut {
  value: number;
  /** The engine's own gate when it reported one; otherwise the donut has no scale and is not drawn. */
  gate: number;
  passes: boolean;
}

/** Pre-period fit relative to the engine's gate. Null without both numbers (no scale to draw against). */
export function fitDonut(items: Evidence[]): FitDonut | null {
  const rel = findEvidence(items, 'fit.relative_pre_rmspe');
  const value = numberValue(rel);
  const gate = numberQualifier(rel, 'gate_threshold');
  if (value === undefined || gate === undefined || !(gate > 0)) return null;
  return { value, gate, passes: value <= gate };
}

export interface PDonut {
  p: number;
  level?: number;
  significant?: boolean;
}

export function pDonut(items: Evidence[], placebos?: PlaceboDistributionData | null): PDonut | null {
  const item = findEvidence(items, 'placebo.p_value');
  const p = numberValue(item) ?? placebos?.pValue;
  if (p === undefined || !Number.isFinite(p)) return null;
  const level = placebos?.significanceLevel ?? numberQualifier(item, 'significance_level');
  return { p, level, significant: level === undefined ? undefined : p <= level };
}

/** Every specification as a dot; the engine's centre specification is the highlighted one. */
export function specDots(curve: SpecCurve): SpecDot[] {
  return curve.estimates.map((e) => ({ value: e.value, main: e.isCentre, flipsSign: e.flipsSign }));
}

/** Spec estimates as raw values, for a histogram. */
export function specValues(curve: SpecCurve): number[] {
  return curve.estimates.map((e) => e.value);
}

/** Synthetic control next to the difference-in-differences estimate; only what was reported. */
export function didVsScm(items: Evidence[]): SignedBar[] {
  const out: SignedBar[] = [];
  const scm = numberValue(findEvidence(items, 'effect.point_estimate'));
  const did = numberValue(findEvidence(items, 'crosscheck.did_estimate'));
  if (scm !== undefined) out.push({ label: 'Synthetic control', value: scm, tone: 'accent' });
  if (did !== undefined) out.push({ label: 'Difference-in-differences', value: did, tone: 'observed' });
  return out;
}

/** The largest single-donor shift next to the size of the estimate, when the run reported it. */
export function leaveOneOutBars(items: Evidence[]): BarItem[] {
  const shift = numberValue(findEvidence(items, 'robustness.max_absolute_shift'));
  const est = numberValue(findEvidence(items, 'effect.point_estimate'));
  if (shift === undefined || est === undefined) return [];
  return [
    { label: 'Size of the estimate', value: Math.abs(est), tone: 'accent', display: sig(Math.abs(est)) },
    { label: 'Largest shift, one donor out', value: Math.abs(shift), tone: 'caution', display: sig(Math.abs(shift)) },
  ];
}

export interface StoryNumber {
  label: string;
  value: string;
  note?: string;
}

/** The three headline numbers for the Story lens; each is omitted when not reported. */
export function storyNumbers(items: Evidence[], placebos?: PlaceboDistributionData | null): StoryNumber[] {
  const out: StoryNumber[] = [];
  const est = findEvidence(items, 'effect.point_estimate');
  if (numberValue(est) !== undefined) out.push({ label: 'Estimated effect', value: withUnit(est) });
  const p = pDonut(items, placebos);
  if (p) out.push({ label: 'Placebo p-value', value: sig(p.p), note: 'chance of a gap this large among untreated areas' });
  const fit = fitDonut(items);
  const rel = numberValue(findEvidence(items, 'fit.relative_pre_rmspe'));
  if (fit) out.push({ label: 'Pre-period fit', value: `${sig(fit.value)} × SD`, note: fit.passes ? 'within the engine gate' : 'outside the engine gate' });
  else if (rel !== undefined) out.push({ label: 'Pre-period fit', value: `${sig(rel)} × SD` });
  return out;
}

/** One plain sentence under the main chart, built only from the reported estimate. */
export function storySentence(items: Evidence[], treatmentYear?: number): string {
  const est = findEvidence(items, 'effect.point_estimate');
  const when = treatmentYear !== undefined && Number.isFinite(treatmentYear) ? `After ${treatmentYear}` : 'After the intervention';
  if (numberValue(est) === undefined) return `${when}, no effect estimate is available for this analysis, so the chart shows the series only.`;
  return `${when}, the project area differs from its counterfactual by an estimated ${withUnit(est)}; read it together with the checks in the Explorer view.`;
}

/** Position of a bounding box inside a padded lat/lon frame, as 0-1 fractions (y grows downward). */
export function bboxRect(bbox: [number, number, number, number]): { x: number; y: number; w: number; h: number; frame: [number, number, number, number] } {
  const [w, s, e, n] = bbox;
  const padX = (e - w) * 0.6 || 0.05;
  const padY = (n - s) * 0.6 || 0.05;
  const frame: [number, number, number, number] = [w - padX, s - padY, e + padX, n + padY];
  const fw = frame[2] - frame[0];
  const fh = frame[3] - frame[1];
  return { x: (w - frame[0]) / fw, y: (frame[3] - n) / fh, w: (e - w) / fw, h: (n - s) / fh, frame };
}
