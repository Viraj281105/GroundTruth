import { Evidence } from './types';
import { DiagnosticGroup, row } from './diagnostics';
import {
  NOT_MEASURED,
  booleanValue,
  checkTone,
  findEvidence,
  numberQualifier,
  numberValue,
  sig,
  withUnit,
} from './evidence';

/**
 * Display model for the in-space placebo, in-time placebo and leave-one-out
 * evidence. The p-value always travels with its floor and significance level:
 * with J placebos the add-one correction makes 1/(J+1) the smallest attainable
 * p-value, so a p-value read without its floor overstates what the test can
 * show.
 */

export interface PValueReading {
  pValue?: number;
  floor?: number;
  significanceLevel?: number;
  rank?: number;
  /** False when even rank 1 could not reach the significance level. */
  canReject?: boolean;
  /** True when the p-value sits at the floor (the project ranks first). */
  atFloor?: boolean;
}

export function readPValue(items: Evidence[]): PValueReading {
  const item = findEvidence(items, 'placebo.p_value');
  const pValue = numberValue(item);
  const floor = numberQualifier(item, 'p_value_floor');
  const significanceLevel = numberQualifier(item, 'significance_level');
  const rank = numberQualifier(item, 'rank');
  return {
    pValue,
    floor,
    significanceLevel,
    rank,
    canReject: floor !== undefined && significanceLevel !== undefined ? floor <= significanceLevel : undefined,
    atFloor: pValue !== undefined && floor !== undefined ? Math.abs(pValue - floor) < 1e-12 : undefined,
  };
}

export function placeboGroup(items: Evidence[]): DiagnosticGroup {
  const reading = readPValue(items);
  const { pValue, floor, significanceLevel, canReject, atFloor } = reading;
  const nUnits = numberValue(findEvidence(items, 'placebo.n_units'));
  const params = findEvidence(items, 'placebo.p_value')?.provenance.parameters ?? {};
  const excludedPoorFit = typeof params.excluded_poor_fit === 'number' ? params.excluded_poor_fit : undefined;

  let status = NOT_MEASURED;
  let tone: DiagnosticGroup['tone'] = 'neutral';
  let summary = 'The in-space placebo was not run for this analysis.';
  if (pValue !== undefined) {
    if (canReject === false) {
      status = 'TOO FEW PLACEBOS TO REJECT';
      summary = `With ${nUnits ?? 'these'} placebo units the smallest attainable p-value is ${sig(floor as number)}, above the significance level of ${sig(significanceLevel as number)}, so this test cannot distinguish the project from untreated regions however large its divergence.`;
    } else if (significanceLevel !== undefined && pValue <= significanceLevel) {
      status = 'BELOW SIGNIFICANCE LEVEL';
      tone = 'positive';
      summary = atFloor
        ? 'No untreated comparison region diverges as much as the project. This is the smallest p-value this many placebos can produce, not evidence of a p-value near zero.'
        : 'Few untreated comparison regions diverge as much as the project.';
    } else {
      status = significanceLevel === undefined ? 'SIGNIFICANCE LEVEL NOT REPORTED' : 'WITHIN PLACEBO RANGE';
      summary =
        'The project’s divergence is within the range seen in untreated comparison regions, so it is not distinguishable from chance variation by this test.';
    }
  }

  return {
    id: 'placebo',
    title: 'In-space placebo',
    summary: `${summary} This is a share of comparison regions, not a probability of misreporting.`,
    status,
    tone,
    rows: [
      row(
        items,
        'placebo.p_value',
        'Permutation p-value',
        () => `p = ${sig(pValue as number)}`,
        () => {
          const parts: string[] = [];
          if (floor !== undefined) parts.push(`Floor 1/(J+1) = ${sig(floor)}`);
          if (significanceLevel !== undefined) parts.push(`α = ${sig(significanceLevel)}`);
          return parts.length > 0 ? parts.join(' · ') : undefined;
        },
      ),
      row(
        items,
        'placebo.n_units',
        'Placebo units (J)',
        (i) => `${i.value} untreated regions`,
        () =>
          reading.rank === undefined
            ? undefined
            : `Project ranks ${reading.rank} of ${(nUnits ?? 0) + 1} by post/pre RMSPE ratio` +
              (excludedPoorFit ? ` · ${excludedPoorFit} excluded for poor pre-fit` : ''),
      ),
    ],
  };
}

export function inTimeGroup(items: Evidence[]): DiagnosticGroup {
  const fake = findEvidence(items, 'placebo.in_time_fake_effect');
  const passes = booleanValue(findEvidence(items, 'placebo.in_time_passes'));
  const period = fake?.qualifiers?.fake_treatment_period;
  const rule = findEvidence(items, 'placebo.in_time_passes')?.provenance.parameters?.pass_rule;

  return {
    id: 'in-time',
    title: 'In-time placebo',
    summary:
      passes === undefined
        ? 'The in-time placebo was not run for this analysis.'
        : passes
          ? `Moving the treatment date back to ${period ?? 'a pre-treatment period'} produces no material effect, so the estimate is not an artefact of where the window splits.`
          : `Moving the treatment date back to ${period ?? 'a pre-treatment period'} produces a material effect where none should exist, which limits how far the estimate can be read as caused by the project.`,
    status: passes === undefined ? NOT_MEASURED : passes ? 'NO MATERIAL SPURIOUS EFFECT' : 'SPURIOUS EFFECT FOUND',
    tone: checkTone(passes),
    rows: [
      row(
        items,
        'placebo.in_time_fake_effect',
        'Effect at the fake treatment date',
        (i) => withUnit(i),
        () => (period === undefined ? undefined : `Fake treatment at period ${period}`),
      ),
      row(
        items,
        'placebo.in_time_passes',
        'Passes the in-time check',
        (i) => (i.value === true ? 'Yes' : 'No'),
        () => (typeof rule === 'string' ? `Rule: ${rule}` : undefined),
      ),
    ],
  };
}

export function leaveOneOutGroup(items: Evidence[]): DiagnosticGroup {
  const stableItem = findEvidence(items, 'robustness.sign_stable');
  const stable = booleanValue(stableItem);
  const nRefits = stableItem?.provenance.parameters?.n_refits;
  const estimate = findEvidence(items, 'effect.point_estimate');

  return {
    id: 'leave-one-out',
    title: 'Leave-one-donor-out',
    summary:
      stable === undefined
        ? 'Leave-one-out refits were not run for this analysis.'
        : stable
          ? 'Removing any single contributing donor leaves the estimate’s sign unchanged, so it does not hinge on one comparison region.'
          : 'Removing a single contributing donor flips the estimate’s sign, so the result depends on one comparison region.',
    status: stable === undefined ? NOT_MEASURED : stable ? 'SIGN STABLE' : 'SIGN CHANGES',
    tone: checkTone(stable),
    rows: [
      row(
        items,
        'robustness.sign_stable',
        'Sign stable across refits',
        (i) => (i.value === true ? 'Yes' : 'No'),
        () => (typeof nRefits === 'number' ? `${nRefits} refits` : undefined),
      ),
      row(
        items,
        'robustness.max_absolute_shift',
        'Largest shift from removing one donor',
        (i) => withUnit(i),
        () => (estimate ? `Point estimate: ${withUnit(estimate)}` : undefined),
      ),
    ],
  };
}

export function derivePlaceboDiagnostics(items: Evidence[]): DiagnosticGroup[] {
  return [placeboGroup(items), inTimeGroup(items), leaveOneOutGroup(items)];
}
