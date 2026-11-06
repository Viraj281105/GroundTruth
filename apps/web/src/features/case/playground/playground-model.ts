import type { ChartDataPoint } from '../../../lib/fixtures/simulated-data';
import type { Evidence } from '../../../lib/types';
import { findEvidence, numberValue } from '../../../lib/evidence';
import { deriveSpecCurve, type SpecEstimate } from '../../../lib/spec-curve';

/**
 * Counterfactual Playground model.
 *
 * Everything shown here is a value the API (or demo fixture) already returned:
 * the observed/synthetic series, the largest donor weights and the engine's own
 * "treatment N periods earlier" specifications. Nothing is recomputed. When a
 * scrubbed year or an excluded donor has no matching engine output the view
 * says so and offers a re-run instead of inventing a number.
 */

export interface PlaygroundState {
  year: number;
  engineYear: number;
  minYear: number;
  maxYear: number;
  /** Donor unit ids switched off. */
  excluded: string[];
}

export type PlaygroundAction =
  | { type: 'setYear'; year: number }
  | { type: 'toggleDonor'; id: string }
  | { type: 'reset' };

export function initialPlaygroundState(engineYear: number, minYear: number, maxYear: number): PlaygroundState {
  const lo = Math.min(minYear, maxYear);
  const hi = Math.max(minYear, maxYear);
  const y = Math.min(Math.max(engineYear, lo), hi);
  return { year: y, engineYear: y, minYear: lo, maxYear: hi, excluded: [] };
}

export function playgroundReducer(state: PlaygroundState, action: PlaygroundAction): PlaygroundState {
  switch (action.type) {
    case 'setYear': {
      if (!Number.isFinite(action.year)) return state;
      const year = Math.min(Math.max(Math.round(action.year), state.minYear), state.maxYear);
      return year === state.year ? state : { ...state, year };
    }
    case 'toggleDonor': {
      const has = state.excluded.includes(action.id);
      return { ...state, excluded: has ? state.excluded.filter((d) => d !== action.id) : [...state.excluded, action.id] };
    }
    case 'reset':
      return { ...state, year: state.engineYear, excluded: [] };
    default:
      return state;
  }
}

export interface DonorWeight {
  id: string;
  weight: number;
  item: Evidence;
}

/** The donor weights the API reported (the largest ones), in reported order. */
export function deriveDonorWeights(items: Evidence[]): DonorWeight[] {
  return items
    .filter((e) => /^fit\.donor_weight\.\d+$/.test(e.id) && typeof e.value === 'number')
    .sort((a, b) => Number(a.id.split('.').pop()) - Number(b.id.split('.').pop()))
    .map((e) => ({
      id: typeof e.qualifiers?.donor_unit_id === 'string' ? e.qualifiers.donor_unit_id : e.id,
      weight: e.value as number,
      item: e,
    }));
}

/** Series with the post-period shading moved to the scrubbed year. */
export function reshadeSeries(series: ChartDataPoint[], year: number): ChartDataPoint[] {
  return series.map((p) => ({ ...p, isPost: p.year > year }));
}

export interface PlaygroundView {
  /** Observed/synthetic/gap at the scrubbed year, as returned. Null if the year is outside the series. */
  point: ChartDataPoint | null;
  /** The engine's own estimate for exactly this treatment year, when it computed one. */
  engineEstimate: { value: number; unit: string; label: string } | null;
  /** Sum of the returned weights of the donors switched off. */
  removedWeight: number | null;
  changed: boolean;
  needsRerun: boolean;
  reason: string | null;
}

function specFor(specs: SpecEstimate[], engineYear: number, year: number): SpecEstimate | null {
  if (year === engineYear) return specs.find((s) => s.isCentre) ?? null;
  const earlier = engineYear - year;
  if (earlier <= 0) return null;
  return specs.find((s) => s.specId === `treatment-${earlier}-earlier`) ?? null;
}

export function derivePlaygroundView(
  state: PlaygroundState,
  series: ChartDataPoint[],
  donors: DonorWeight[],
  items: Evidence[],
): PlaygroundView {
  const curve = deriveSpecCurve(items);
  const specs = curve?.estimates ?? [];
  const spec = specFor(specs, state.engineYear, state.year);
  const yearChanged = state.year !== state.engineYear;
  const donorsChanged = state.excluded.length > 0;
  const known = donors.filter((d) => state.excluded.includes(d.id));
  const removedWeight = donorsChanged && known.length > 0 ? known.reduce((s, d) => s + d.weight, 0) : null;

  let reason: string | null = null;
  if (donorsChanged) {
    reason = 'Removing donors changes the synthetic control. The API returns no estimate for that pool, so none is shown.';
  } else if (yearChanged && !spec) {
    reason = 'The engine did not compute an estimate for this treatment year, so none is shown.';
  }

  return {
    point: series.find((p) => p.year === state.year) ?? null,
    engineEstimate: spec && !donorsChanged ? { value: spec.value, unit: curve?.unit ?? '', label: spec.label } : null,
    removedWeight,
    changed: yearChanged || donorsChanged,
    needsRerun: reason !== null,
    reason,
  };
}

/** Treatment boundary the engine used, falling back to the first post-period year. */
export function engineTreatmentYear(items: Evidence[], series: ChartDataPoint[]): number | null {
  const fromEvidence = numberValue(findEvidence(items, 'fit.treatment_boundary_period'));
  if (fromEvidence !== undefined) return fromEvidence;
  const firstPost = series.find((p) => p.isPost);
  return firstPost ? firstPost.year - 1 : null;
}

export function rerunHref(caseId: string, state: PlaygroundState): string {
  const q = new URLSearchParams();
  if (state.year !== state.engineYear) q.set('treatment_year', String(state.year));
  if (state.excluded.length > 0) q.set('exclude_donors', state.excluded.join(','));
  const qs = q.toString();
  return `/cases/${encodeURIComponent(caseId)}/run${qs ? `?${qs}` : ''}`;
}
