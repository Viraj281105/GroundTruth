import { Evidence } from './types';
import { CheckTone, findEvidence, listQualifier, numberQualifier, numberValue, sig } from './evidence';

/**
 * Display model for the in-run specification curve (engine PR #69).
 *
 * The curve is a one-at-a-time sweep around the request's own specification.
 * The centre is marked but not privileged: the median, sign agreement and
 * range are computed by the engine over every specification, and the UI
 * presents them that way — the centre is one point among the others, never
 * the headline.
 *
 * The range is a sensitivity envelope (the spread of estimates across
 * analytic choices), not a confidence interval, so it is never printed with a
 * confidence level.
 */

const ESTIMATE_PREFIX = 'robustness.spec_curve.estimate.';

const DIMENSION_LABELS: Record<string, string> = {
  centre: 'Centre',
  ridge: 'Ridge penalty',
  pre_period_length: 'Pre-period length',
  treatment_date: 'Treatment date',
  donor_cap: 'Donor cap',
  indicator: 'Indicator',
  caliper: 'Caliper',
  covariate_weighting: 'Covariate weighting',
};

export function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension.replace(/_/g, ' ');
}

/** Human-readable name for a specification id emitted by the engine. */
export function specLabel(specId: string): string {
  if (specId === 'centre') return 'Centre (the request’s own specification)';
  let m = /^ridge-(.+)$/.exec(specId);
  if (m) return `Ridge penalty ${m[1].replace(/-/g, '.')}`;
  m = /^pre-period-(\d+)$/.exec(specId);
  if (m) return `${m[1]} pre-treatment periods`;
  m = /^treatment-(\d+)-earlier$/.exec(specId);
  if (m) return `Treatment ${m[1]} period${m[1] === '1' ? '' : 's'} earlier`;
  m = /^donor-cap-(\d+)$/.exec(specId);
  if (m) return `${m[1]} nearest donors`;
  return specId;
}

export interface SpecEstimate {
  specId: string;
  label: string;
  dimension: string;
  value: number;
  isCentre: boolean;
  flipsSign: boolean;
  item: Evidence;
}

export interface SpecCurve {
  unit: string;
  median: number;
  medianItem: Evidence;
  /** Smallest and largest estimate across specifications. */
  range?: { lower: number; upper: number };
  signAgreement?: number;
  signAgreementItem?: Evidence;
  signFlips: string[];
  /** Ascending by estimate, as the engine orders them. */
  estimates: SpecEstimate[];
  nSpecifications: number;
  nFailed: number;
  dimensionsVaried: string[];
  dimensionsNotVaried: string[];
  status: string;
  tone: CheckTone;
  summary: string;
}

function stringList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
}

/** The specification curve, or `null` when the run did not compute one. */
export function deriveSpecCurve(items: Evidence[]): SpecCurve | null {
  const medianItem = findEvidence(items, 'robustness.spec_curve.median');
  const median = numberValue(medianItem);
  if (medianItem === undefined || median === undefined) return null;

  const agreementItem = findEvidence(items, 'robustness.spec_curve.sign_agreement');
  const signAgreement = numberValue(agreementItem);
  const signFlips = stringList(listQualifier(agreementItem, 'sign_flips'));
  const params = medianItem.provenance.parameters ?? {};

  const estimates: SpecEstimate[] = items
    .filter((e) => e.id.startsWith(ESTIMATE_PREFIX) && typeof e.value === 'number')
    .map((e) => {
      const specId = e.id.slice(ESTIMATE_PREFIX.length);
      return {
        specId,
        label: specLabel(specId),
        dimension: typeof e.qualifiers?.dimension === 'string' ? e.qualifiers.dimension : 'unknown',
        value: e.value as number,
        isCentre: e.qualifiers?.is_centre === true,
        flipsSign: e.qualifiers?.flips_sign === true,
        item: e,
      };
    })
    .sort((a, b) => a.value - b.value);

  const range = medianItem.confidence
    ? { lower: medianItem.confidence.lower, upper: medianItem.confidence.upper }
    : undefined;
  const nSpecifications =
    numberQualifier(medianItem, 'n_specifications') ??
    (typeof params.n_specifications === 'number' ? params.n_specifications : estimates.length);
  const nFailed = typeof params.n_failed === 'number' ? params.n_failed : 0;

  const stable = signFlips.length === 0;
  const unit = medianItem.unit;
  const rangeText = range ? ` and range from ${sig(range.lower)} to ${sig(range.upper)} ${unit}`.trimEnd() : '';
  const summary = stable
    ? `Every one of the ${nSpecifications} specifications gives an estimate with the same sign as the median${rangeText}. The finding does not depend on any single analytic choice varied here.`
    : `${signFlips.length} of ${nSpecifications} specifications give the opposite sign to the median (${signFlips
        .map(specLabel)
        .join(', ')}). The direction of the estimate depends on analytic choices, which is a limitation of the result for this case.`;

  return {
    unit,
    median,
    medianItem,
    range,
    signAgreement,
    signAgreementItem: agreementItem,
    signFlips,
    estimates,
    nSpecifications,
    nFailed,
    dimensionsVaried: stringList(params.dimensions_varied),
    dimensionsNotVaried: stringList(params.dimensions_not_varied_in_run),
    status: stable ? 'SIGN AGREES ACROSS SPECIFICATIONS' : 'SIGN DEPENDS ON SPECIFICATION',
    tone: stable ? 'positive' : 'caution',
    summary,
  };
}

/** "0.0546 ndvi; range 0.0506 to 0.0587 ndvi across 7 specifications (sensitivity envelope, not a confidence interval)". */
export function formatSpecCurveMedian(curve: SpecCurve): string {
  const base = `${sig(curve.median)} ${curve.unit}`.trim();
  if (!curve.range) return base;
  return `${base}; range ${sig(curve.range.lower)} to ${sig(curve.range.upper)} ${curve.unit} across ${curve.nSpecifications} specifications (sensitivity envelope, not a confidence interval)`;
}

export function formatSignAgreement(curve: SpecCurve): string {
  if (curve.signAgreement === undefined) return 'Not measured';
  return `${sig(curve.signAgreement * 100)}% of specifications`;
}
