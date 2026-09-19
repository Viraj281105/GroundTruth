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
