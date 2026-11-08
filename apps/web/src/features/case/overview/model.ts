import type { RefusalInfo } from '../../../lib/api';
import type { VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import { findEvidence, numberValue } from '../../../lib/evidence';
import { formatConfidenceInterval, formatDivergenceRatio, formatEvidenceValue, formatPValue } from '../../../lib/formatters';
import type { CaseDetail, Confidence, VerdictLabel } from '../../../lib/types';
import { overviewCopy as c } from './copy';
import { buildSparkline, type Sparkline } from './sparkline';
import { buildFigures, NO_FIGURES, type OverviewFigures } from './figures';

export type OverviewKind = 'measured' | 'inconclusive' | 'refused' | 'not_run';

export interface HeadlineEffect {
  valueText: string;
  /** Interval with its kind, from the API's own formatter; null when none was returned. */
  intervalText: string | null;
  /** Plain-language sentence for the Story lens. Only numbers the API returned. */
  plain: string;
}

export interface OverviewModel {
  kind: OverviewKind;
  verdictLabel: VerdictLabel | null;
  divergenceText: string | null;
  rationale: string | null;
  caveats: string[];
  headline: HeadlineEffect | null;
  facts: { donors: string; fit: string; placebo: string };
  chart: Sparkline | null;
  figures: OverviewFigures;
  refusal: RefusalInfo | null;
  provenance: { runId: string; specHash: string; dataMode: string; engineVersion: string; contractVersion: string; evidenceCount: number } | null;
}

/** A plain-language reading of the effect and its uncertainty, using only returned numbers. */
export function describeEffect(valueText: string, confidence: Confidence | null, interval: string | null): string {
  if (!confidence || !interval) {
    return `The best estimate of the project's effect is ${valueText}. No uncertainty range was returned for it, so it should not be read as precise.`;
  }
  if (confidence.kind === 'sensitivity-envelope') {
    return `The best estimate of the project's effect is ${valueText}. Across the analysis choices tried, it ranged from ${confidence.lower.toFixed(4)} to ${confidence.upper.toFixed(4)}. This is a range of estimates, not a confidence interval.`;
  }
  if (confidence.kind === 'assumed-1sigma-interval') {
    return `The best estimate is ${valueText}. Under an assumed model error, a one-sigma range (about 68%, not a 95% confidence interval) runs from ${confidence.lower.toFixed(4)} to ${confidence.upper.toFixed(4)}.`;
  }
  const pct = Math.round(confidence.level * 100);
  return `The best estimate of the project's effect is ${valueText}. Allowing for uncertainty, the ${pct}% ${confidence.kind} interval runs from ${confidence.lower.toFixed(4)} to ${confidence.upper.toFixed(4)}.`;
}

function treatmentYearOf(detail: CaseDetail, fixture: VerificationFixtureData): number | undefined {
  const fromBundle = numberValue(findEvidence(fixture.verification.bundle.items, 'fit.treatment_boundary_period'));
  if (fromBundle !== undefined) return fromBundle;
  const parsed = parseInt(detail.post_period.split('-')[0], 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function buildOverviewModel(
  detail: CaseDetail,
  fixture: VerificationFixtureData | null,
  refusal: RefusalInfo | null,
): OverviewModel {
  const donors = Number.isFinite(detail.donor_pool_size) ? detail.donor_pool_size.toLocaleString('en-US') : c.notMeasured;
  const empty: OverviewModel = {
    kind: 'not_run',
    verdictLabel: null,
    divergenceText: null,
    rationale: null,
    caveats: [],
    headline: null,
    facts: { donors, fit: c.notMeasured, placebo: c.notMeasured },
    chart: null,
    figures: NO_FIGURES,
    refusal: null,
    provenance: null,
  };
  if (refusal) return { ...empty, kind: 'refused', refusal };
  const verdict = fixture?.verification.bundle.verdict ?? null;
  if (!fixture || !verdict) return empty;

  const items = fixture.verification.bundle.items;
  const effect = findEvidence(items, 'effect.point_estimate');
  const preFit = findEvidence(items, 'fit.pre_rmspe');
  const pValue = numberValue(findEvidence(items, 'placebo.p_value'));

  let headline: HeadlineEffect | null = null;
  if (effect) {
    const valueText = formatEvidenceValue(effect.value, effect.unit || null);
    const interval = effect.confidence ? formatConfidenceInterval(effect.confidence, effect.unit || undefined) : null;
    headline = { valueText, intervalText: interval, plain: describeEffect(valueText, effect.confidence, interval) };
  }

  const v = fixture.verification;
  return {
    kind: verdict.label === 'inconclusive' ? 'inconclusive' : 'measured',
    verdictLabel: verdict.label,
    divergenceText: verdict.divergence_ratio != null ? formatDivergenceRatio(verdict.divergence_ratio) : null,
    rationale: verdict.rationale,
    caveats: verdict.caveats,
    headline,
    facts: {
      donors,
      fit: preFit ? formatEvidenceValue(preFit.value, preFit.unit || null) : c.notMeasured,
      placebo: pValue !== undefined ? formatPValue(pValue) : c.notMeasured,
    },
    chart: buildSparkline(fixture.chartSeries, treatmentYearOf(detail, fixture)),
    figures: buildFigures(fixture, treatmentYearOf(detail, fixture)),
    refusal: null,
    provenance: {
      runId: v.run_id,
      specHash: v.spec_hash,
      dataMode: v.data_mode,
      engineVersion: v.engine_version,
      contractVersion: v.contract_version,
      evidenceCount: items.length,
    },
  };
}
