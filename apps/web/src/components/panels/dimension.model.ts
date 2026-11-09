import type { DimensionView } from './types';

export type DimTone = 'positive' | 'caution' | 'danger' | 'neutral' | 'mixed' | 'insufficient';
export type DimKind = 'trend' | 'quality' | 'verdict';

const TREND = {
  Improving: { tone: 'positive', icon: '▲' },
  Deteriorating: { tone: 'caution', icon: '▼' },
  Stable: { tone: 'neutral', icon: '▬' },
  'Mixed spatial performance': { tone: 'mixed', icon: '◐' },
  'Elevated ecological risk': { tone: 'danger', icon: '◆' },
  'No clear change': { tone: 'neutral', icon: '○' },
  'Insufficient evidence': { tone: 'insufficient', icon: '◌' },
} as const satisfies Record<string, { tone: DimTone; icon: string }>;
export type TrendStatus = keyof typeof TREND;

export interface DimensionStatusView {
  kind: DimKind;
  tone: DimTone;
  label: string;
  /** A text glyph with its own shape per status, so meaning never rests on colour alone. */
  icon: string;
  /** Set when `kind === 'trend'` and the status is one the StatusChip knows. */
  chipStatus: TrendStatus | null;
}

const QUALITY: Record<string, { tone: DimTone; icon: string }> = {
  High: { tone: 'positive', icon: '■' },
  Moderate: { tone: 'neutral', icon: '▣' },
  Low: { tone: 'caution', icon: '□' },
};
const VERDICT: Record<string, { tone: DimTone; icon: string }> = {
  Supported: { tone: 'positive', icon: '✓' },
  'Not supported': { tone: 'caution', icon: '✕' },
  Inconclusive: { tone: 'insufficient', icon: '◌' },
};

const UNKNOWN: { tone: DimTone; icon: string } = { tone: 'insufficient', icon: '◌' };

/**
 * Maps a dimension's `status_kind` + `status` to its treatment. Unknown statuses fall back to the
 * neutral "insufficient" look: never a success treatment for anything the UI does not recognise.
 */
export function dimensionView(d: Pick<DimensionView, 'status' | 'status_kind'>): DimensionStatusView {
  const label = d.status;
  if (d.status_kind === 'quality_rating') {
    return { kind: 'quality', label, chipStatus: null, ...(QUALITY[label] ?? UNKNOWN) };
  }
  if (d.status_kind === 'attribution_verdict') {
    return { kind: 'verdict', label, chipStatus: null, ...(VERDICT[label] ?? UNKNOWN) };
  }
  const known = Object.prototype.hasOwnProperty.call(TREND, label);
  const t: { tone: DimTone; icon: string } = known ? TREND[label as TrendStatus] : UNKNOWN;
  return { kind: 'trend', label, chipStatus: known ? (label as TrendStatus) : null, tone: t.tone, icon: t.icon };
}

const LIMITATIONS: Record<string, string> = {
  missing_data: 'Missing data',
  weak_statistical_power: 'Weak statistical power',
  poor_reference_comparability: 'Poor reference comparability',
  climate_confounding: 'Climate confounding',
  failed_model_assumptions: 'Failed model assumptions',
  none: 'No limitation',
};

export function limitationLabel(limitation: string): string {
  return LIMITATIONS[limitation] ?? limitation.replace(/_/g, ' ');
}
