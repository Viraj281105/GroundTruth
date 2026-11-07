import type { VerificationFixtureData } from '../../lib/fixtures/simulated-data';

/** Numbers drawn from a (simulated) run fixture. Every field is null when the run did not provide it (R5). */
export interface CaseViz {
  observed: number[];
  gap: { x: number; y: number }[];
  treatmentYear: number | null;
  indicator: string | null;
  effect: number | null;
  /** Min/max of the robustness specification curve; null if fewer than two specifications. */
  specLow: number | null;
  specHigh: number | null;
  donorsAdmitted: number | null;
  donorsCandidates: number | null;
  relPreRmspe: number | null;
  placeboP: number | null;
}

function item(f: VerificationFixtureData, id: string) {
  return f.verification.bundle.items.find((e) => e.id === id);
}

function numeric(f: VerificationFixtureData, id: string): number | null {
  const v = item(f, id)?.value;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function buildCaseViz(f: VerificationFixtureData | null): CaseViz | null {
  if (!f) return null;
  const series = Array.isArray(f.chartSeries)
    ? f.chartSeries.filter((p) => Number.isFinite(p.observed) && Number.isFinite(p.synthetic))
    : [];
  const spec = f.verification.bundle.items
    .filter((e) => e.id.startsWith('robustness.spec_curve.estimate.') && typeof e.value === 'number' && Number.isFinite(e.value))
    .map((e) => e.value as number);
  const post = series.find((p) => p.isPost);
  return {
    observed: series.map((p) => p.observed),
    gap: series.map((p) => ({ x: p.year, y: p.gap })),
    treatmentYear: post ? post.year : numeric(f, 'fit.treatment_boundary_period'),
    indicator: item(f, 'effect.point_estimate')?.unit ?? null,
    effect: numeric(f, 'effect.point_estimate'),
    specLow: spec.length >= 2 ? Math.min(...spec) : null,
    specHigh: spec.length >= 2 ? Math.max(...spec) : null,
    donorsAdmitted: numeric(f, 'matching.n_donors_admitted'),
    donorsCandidates: numeric(f, 'matching.n_candidates'),
    relPreRmspe: numeric(f, 'fit.relative_pre_rmspe'),
    placeboP: numeric(f, 'placebo.p_value'),
  };
}

/** Observed series per case id, only for cases whose fixture has one with at least two points. */
export function observedSeriesMap(
  ids: string[],
  get: (id: string) => VerificationFixtureData | null,
): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  for (const id of ids) {
    const v = buildCaseViz(get(id));
    if (v && v.observed.length >= 2) out[id] = v.observed;
  }
  return out;
}
