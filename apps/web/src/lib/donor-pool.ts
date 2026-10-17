import { Evidence } from './types';
import { DiagnosticGroup, row } from './diagnostics';
import { NOT_MEASURED, booleanValue, checkTone, findEvidence, numberQualifier, numberValue, sig } from './evidence';

/**
 * Display model for the donor pool: matching counts, covariate balance, the
 * contributing donors' weights, and per-candidate exclusions grouped by the
 * eligibility rule that removed them.
 *
 * Everything except the per-candidate table is read from the evidence bundle.
 * The table comes from `not_served_by_api.donor_pool` in the generated
 * fixture, because `AnalysisResult` does not carry the candidate list; on a
 * real response only the exclusion count is available, and the UI says so.
 *
 * There is no geography here. The engine matches in standardised covariate
 * space and the synthetic provider has no coordinates, so a map would have to
 * invent them.
 */

export type ExclusionRule = 'leakage_belt' | 'common_support' | 'pre_treatment_coverage' | 'donor_cap' | 'other';

export const EXCLUSION_RULE_LABELS: Record<ExclusionRule, string> = {
  leakage_belt: 'Inside the leakage belt',
  common_support: 'Outside common support',
  pre_treatment_coverage: 'Too few clear pre-treatment scenes',
  donor_cap: 'Beyond the donor cap',
  other: 'Other rule',
};

export const EXCLUSION_RULE_DESCRIPTIONS: Record<ExclusionRule, string> = {
  leakage_belt: 'Could have received displaced activity from the project, so it may be treated in disguise.',
  common_support: 'Too far from the project on a covariate to compare without extrapolating.',
  pre_treatment_coverage: 'Lacks enough clear observations in every pre-period to fit weights on.',
  donor_cap: 'Eligible, but ranked past the maximum number of donors by covariate distance.',
  other: 'Excluded by a rule this view does not yet group.',
};

/** Map an engine exclusion reason to the rule that produced it. */
export function exclusionRule(reason: string): ExclusionRule {
  if (reason.startsWith('inside project leakage belt')) return 'leakage_belt';
  if (reason.startsWith('outside common support')) return 'common_support';
  if (reason.startsWith('insufficient clear pre-treatment observations')) return 'pre_treatment_coverage';
  if (/beyond the max_donors cap/.test(reason)) return 'donor_cap';
  return 'other';
}

export interface Candidate {
  unit_id: string;
  admitted: boolean;
  distance: number;
  exclusion_reason: string | null;
}

export interface ExclusionGroup {
  rule: ExclusionRule;
  label: string;
  description: string;
  candidates: Candidate[];
}

const RULE_ORDER: ExclusionRule[] = ['leakage_belt', 'common_support', 'pre_treatment_coverage', 'donor_cap', 'other'];

export function groupExclusions(candidates: Candidate[]): ExclusionGroup[] {
  const byRule = new Map<ExclusionRule, Candidate[]>();
  for (const c of candidates) {
    if (c.admitted || !c.exclusion_reason) continue;
    const rule = exclusionRule(c.exclusion_reason);
    byRule.set(rule, [...(byRule.get(rule) ?? []), c]);
  }
  return RULE_ORDER.filter((r) => byRule.has(r)).map((rule) => ({
    rule,
    label: EXCLUSION_RULE_LABELS[rule],
    description: EXCLUSION_RULE_DESCRIPTIONS[rule],
    candidates: byRule.get(rule) ?? [],
  }));
}

function countOf(item: Evidence, noun: string): string {
  const n = numberValue(item);
  return n === undefined ? NOT_MEASURED : `${n} ${noun}${n === 1 ? '' : 's'}`;
}

export function poolGroup(items: Evidence[]): DiagnosticGroup {
  const admitted = numberValue(findEvidence(items, 'matching.n_donors_admitted'));
  const smd = findEvidence(items, 'matching.worst_covariate_smd');
  const balancedQ = smd?.qualifiers?.balanced;
  const balanced = typeof balancedQ === 'boolean' ? balancedQ : undefined;
  const threshold = numberQualifier(smd, 'guideline_threshold');
  const covariates = smd?.provenance.parameters?.covariates;
  const nCovariates = Array.isArray(covariates) ? covariates.length : undefined;

  return {
    id: 'pool',
    title: 'Donor pool',
    summary:
      admitted === undefined
        ? 'Donor matching was not reported for this run.'
        : balanced === false
          ? 'At least one covariate is out of balance after matching, so the comparison regions differ systematically from the project on it.'
          : 'Candidates were screened by explicit eligibility rules, and every covariate is within the balance guideline after matching.',
    status: balanced === undefined ? NOT_MEASURED : balanced ? 'BALANCED' : 'IMBALANCED',
    tone: checkTone(balanced),
    rows: [
      row(items, 'matching.n_candidates', 'Candidate regions considered', (i) => countOf(i, 'region')),
      row(items, 'matching.n_donors_admitted', 'Admitted to the donor pool', (i) => countOf(i, 'region')),
      row(items, 'matching.n_candidates_excluded', 'Excluded by an eligibility rule', (i) => countOf(i, 'region')),
      row(
        items,
        'matching.worst_covariate_smd',
        'Worst covariate imbalance after matching',
        (i) => `${sig(Number(i.value))} SMD`,
        () =>
          [
            threshold !== undefined ? `Guideline: at most ${sig(threshold)} SMD` : null,
            nCovariates !== undefined ? `across ${nCovariates} covariates` : null,
          ]
            .filter(Boolean)
            .join(' ') || undefined,
      ),
    ],
  };
}

export function weightsGroup(items: Evidence[]): DiagnosticGroup {
  const weightItems = items
    .filter((e) => /^fit\.donor_weight\.\d+$/.test(e.id))
    .sort((a, b) => Number(a.id.split('.').pop()) - Number(b.id.split('.').pop()));
  const identified = booleanValue(findEvidence(items, 'fit.weights_identified'));

  return {
    id: 'weights',
    title: 'Contributing donors',
    summary:
      weightItems.length === 0
        ? 'Donor weights were not reported for this run.'
        : `The ${weightItems.length} largest weights in the synthetic control. Weights are non-negative and sum to one across all donors.`,
    status: identified === undefined ? NOT_MEASURED : identified ? 'WEIGHTS UNIQUE' : 'WEIGHTS NOT UNIQUE',
    tone: 'neutral',
    caveats:
      identified === false
        ? [
            'There are more donors than pre-treatment periods, so these weights are one of several equally good weightings. The counterfactual path and the estimate are still determined; read the list as an illustration of the comparison set.',
          ]
        : [],
    rows: weightItems.map((w) => ({
      evidenceId: w.id,
      label: typeof w.qualifiers?.donor_unit_id === 'string' ? w.qualifiers.donor_unit_id : w.id,
      display: `${sig(Number(w.value) * 100)}% of the synthetic control`,
      detail: `Weight ${sig(Number(w.value))}`,
      item: w,
    })),
  };
}

export function deriveDonorPool(items: Evidence[]): DiagnosticGroup[] {
  return [poolGroup(items), weightsGroup(items)];
}
