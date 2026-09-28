import { Confidence, Evidence } from './types';

/**
 * Format an evidence value with its unit.
 * RULE: No bare numbers. Every displayed value shows its unit.
 */
export function formatEvidenceValue(value: number | string | boolean, unit?: string | null): string {
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'number') {
    // Format floats to sensible scientific precision, preserving integers
    const formatted = Number.isInteger(value)
      ? value.toLocaleString('en-US')
      : Math.abs(value) < 0.001 && value !== 0
      ? value.toExponential(3)
      : value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    return unit ? `${formatted} ${unit}` : formatted;
  }
  return unit ? `${value} ${unit}` : String(value);
}

/**
 * Format a confidence interval with its kind.
 * RULE: Confidence intervals must state their kind ('permutation', 'sensitivity-envelope', etc.)
 * as they are not interchangeable.
 */
export function formatConfidenceInterval(confidence: Confidence | null, unit?: string): string {
  if (!confidence) return '';
  const lower = confidence.lower.toFixed(4);
  const upper = confidence.upper.toFixed(4);
  const levelPct = Math.round(confidence.level * 100);
  const unitStr = unit ? ` ${unit}` : '';
  return `[${lower}, ${upper}${unitStr}] (${levelPct}% ${confidence.kind})`;
}

/**
 * Format hectares with thousands separator.
 */
export function formatHectares(ha: number | null | undefined): string {
  if (ha === null || ha === undefined) return 'Unspecified';
  return `${ha.toLocaleString('en-US')} ha`;
}

/**
 * Format a divergence ratio safely without sensationalism.
 */
export function formatDivergenceRatio(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return 'N/A';
  return `${ratio.toFixed(2)}x`;
}

/**
 * Format permutation p-value.
 */
export function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined) return 'N/A';
  if (p < 0.001) return 'p < 0.001';
  return `p = ${p.toFixed(3)}`;
}

/**
 * Format Standardised Mean Difference (SMD) with balance status.
 */
export function formatSMD(smd: number, threshold = 0.25): { formatted: string; isBalanced: boolean } {
  return {
    formatted: `${smd.toFixed(3)} SMD`,
    isBalanced: Math.abs(smd) <= threshold,
  };
}

/**
 * Format a count or scalar measurement that may not exist yet.
 * RULE: the absence of a measurement is an explicit state, never a zero.
 * `0` is a legitimate measured value (e.g. "0 admitted donors" is a real
 * finding) and must render as `0`; only `null`/`undefined` render as
 * "Not measured".
 */
export function formatMeasurement(value: number | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return 'Not measured';
  const formatted = value.toLocaleString('en-US');
  return unit ? `${formatted} ${unit}` : formatted;
}

/**
 * The following four functions derive display strings for the "Scientific
 * Conclusion" summary cards from real evidence items only. RULE: a missing
 * evidence item (or a missing parameter/qualifier on one that is present)
 * renders as "Not measured" — never as a plausible-looking placeholder
 * number, regardless of whether the underlying run was real or simulated.
 */

/** "Permutation Significance", from the `placebo.p_value` evidence item. */
export function formatPermutationSignificance(items: Evidence[]): string {
  const item = items.find((i) => i.id === 'placebo.p_value');
  return typeof item?.value === 'number' ? formatPValue(item.value) : 'Not measured';
}

/**
 * "Donor Jackknife Stability", from the `robustness.sign_stable` evidence
 * item and its `n_refits` provenance parameter (set by
 * `engine/assembler.py` from the actual leave-one-out refit count, not a
 * fixture-only value).
 */
export function formatJackknifeStability(items: Evidence[]): string {
  const item = items.find((i) => i.id === 'robustness.sign_stable');
  if (typeof item?.value !== 'boolean') return 'Not measured';
  const nRefits = item.provenance.parameters?.n_refits;
  const refitsText = typeof nRefits === 'number' ? `${nRefits} refits` : 'an unrecorded number of refits';
  return `${item.value ? 'Stable' : 'Not stable'} across ${refitsText}`;
}

/**
 * "DiD Parallel Pre-Trends", from the `crosscheck.did_estimate` item's
 * `parallel_trends_plausible` qualifier and the separate
 * `crosscheck.did_pre_trend_divergence` evidence item.
 */
export function formatDidParallelTrends(items: Evidence[]): string {
  const estimateItem = items.find((i) => i.id === 'crosscheck.did_estimate');
  const divergenceItem = items.find((i) => i.id === 'crosscheck.did_pre_trend_divergence');
  const plausible = estimateItem?.qualifiers?.parallel_trends_plausible;
  if (typeof plausible !== 'boolean') return 'Not measured';
  const divergenceText =
    typeof divergenceItem?.value === 'number' ? ` (Div: ${divergenceItem.value.toFixed(4)})` : '';
  return `${plausible ? 'Plausible' : 'Implausible'}${divergenceText}`;
}

/**
 * Compact uncertainty envelope for the causal-pipeline stage card, from the
 * `effect.point_estimate` evidence item's own confidence interval. Returns
 * `''` (not a fabricated range) when no confidence interval was produced.
 */
export function formatUncertaintyEnvelope(confidence: Confidence | null | undefined): string {
  if (!confidence) return '';
  return `[${confidence.lower.toFixed(3)}, ${confidence.upper.toFixed(3)}]`;
}
