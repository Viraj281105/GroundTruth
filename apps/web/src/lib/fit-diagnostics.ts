import { Evidence } from './types';
import { DiagnosticGroup, row } from './diagnostics';
import {
  NOT_MEASURED,
  booleanValue,
  checkTone,
  findEvidence,
  listQualifier,
  numberQualifier,
  numberValue,
  sig,
  withUnit,
} from './evidence';

/**
 * Display model for the pre-treatment fit, convex-hull and period-coverage
 * evidence (engine PRs #65-#66 and the alignment stage). Pure, so the copy and
 * the pass/fail reading are tested without rendering.
 */

function periodRange(item: Evidence): string | undefined {
  const first = item.qualifiers?.first_period;
  const last = item.qualifiers?.last_period;
  return first !== undefined && last !== undefined ? `${first}–${last}` : undefined;
}

function countOf(item: Evidence, noun: string): string {
  const n = numberValue(item);
  return n === undefined ? withUnit(item) : `${n} ${noun}${n === 1 ? '' : 's'}`;
}

export function fitGroup(items: Evidence[]): DiagnosticGroup {
  const relative = findEvidence(items, 'fit.relative_pre_rmspe');
  const value = numberValue(relative);
  const gate = numberQualifier(relative, 'gate_threshold');
  const passes = value !== undefined && gate !== undefined ? value <= gate : undefined;

  return {
    id: 'fit',
    title: 'Pre-treatment fit',
    summary:
      passes === undefined
        ? 'The fit gate was not reported for this run.'
        : passes
          ? 'The synthetic control tracks the project closely before treatment, relative to the project’s own year-to-year variation.'
          : 'The synthetic control does not track the project closely enough before treatment, so the post-treatment gap cannot be read as an effect.',
    status: passes === undefined ? NOT_MEASURED : passes ? 'WITHIN FIT GATE' : 'OUTSIDE FIT GATE',
    tone: checkTone(passes),
    rows: [
      row(
        items,
        'fit.relative_pre_rmspe',
        'Pre-treatment RMSPE relative to outcome SD',
        (i) => `${sig(Number(i.value))} × pre-period SD`,
        () => (gate === undefined ? undefined : `Gate: at most ${sig(gate)} × SD`),
      ),
      row(items, 'fit.pre_rmspe', 'Pre-treatment RMSPE', (i) => `${sig(Number(i.value))} ${i.unit}`.trim()),
      row(
        items,
        'fit.rmspe_ratio',
        'Post/pre RMSPE ratio',
        (i) => `${sig(Number(i.value))}× (ratio)`,
        () => 'Test statistic for the in-space placebo',
      ),
    ],
  };
}

export function hullGroup(items: Evidence[]): DiagnosticGroup {
  const inside = booleanValue(findEvidence(items, 'fit.inside_donor_hull'));
  return {
    id: 'hull',
    title: 'Convex-hull containment',
    summary:
      inside === undefined
        ? 'The convex-hull diagnostic was not reported for this run.'
        : inside
          ? 'The project’s pre-treatment path lies within the range its donors can reproduce, so the weights need not extrapolate.'
          : 'The project’s pre-treatment path lies outside what any weighting of its donors can reproduce, so every post-treatment gap carries a structural offset. The donor pool is inadequate for this project as specified.',
    status: inside === undefined ? NOT_MEASURED : inside ? 'INSIDE DONOR HULL' : 'OUTSIDE DONOR HULL',
    tone: checkTone(inside),
    rows: [
      row(items, 'fit.inside_donor_hull', 'Pre-treatment path within donors’ hull', (i) =>
        i.value === true ? 'Yes' : 'No',
      ),
      row(
        items,
        'fit.hull_level_excess',
        'Pre-period mean outside the donor range',
        (i) => `${sig(Number(i.value))} ${i.unit}`.trim(),
        (i) => {
          const sd = numberQualifier(i, 'in_pre_period_sd');
          return sd === undefined ? undefined : `${sig(sd)} × pre-period SD`;
        },
      ),
      row(
        items,
        'fit.hull_periods_outside_envelope',
        'Pre-periods outside every donor’s range',
        (i) => `${sig(Number(i.value) * 100)}% of pre-periods`,
        (i) => {
          const max = numberQualifier(i, 'max_excess');
          const unit = findEvidence(items, 'fit.hull_level_excess')?.unit ?? '';
          return max === undefined ? undefined : `Largest excess: ${sig(max)} ${unit}`.trim();
        },
      ),
    ],
  };
}

export function coverageGroup(items: Evidence[]): DiagnosticGroup {
  const boundary = findEvidence(items, 'fit.treatment_boundary_period');
  const dropped = listQualifier(boundary, 'dropped_periods');
  const measured = boundary !== undefined;
  return {
    id: 'coverage',
    title: 'Period coverage',
    summary: !measured
      ? 'Period coverage was not reported for this run.'
      : dropped && dropped.length > 0
        ? `Every included series covers the full window. Periods ${dropped.join(', ')} were returned by the data provider but fall outside the window, so no estimator used them.`
        : 'Every included series covers every period of the window; the pre/post split is taken from period labels.',
    status: measured ? 'FULL WINDOW COVERED' : NOT_MEASURED,
    // Coverage is a precondition, not a quality signal: a run that reached
    // assembly has always passed it, so it is reported neutrally.
    tone: 'neutral',
    rows: [
      row(items, 'fit.n_pre_periods', 'Pre-treatment periods', (i) => countOf(i, 'period'), periodRange),
      row(items, 'fit.n_post_periods', 'Post-treatment periods', (i) => countOf(i, 'period'), periodRange),
      row(
        items,
        'fit.treatment_boundary_period',
        'First post-treatment period',
        (i) => `Period ${i.value}`,
        () => (dropped && dropped.length > 0 ? `Dropped: ${dropped.join(', ')}` : 'No periods dropped'),
      ),
    ],
  };
}

export function deriveFitDiagnostics(items: Evidence[]): DiagnosticGroup[] {
  return [fitGroup(items), hullGroup(items), coverageGroup(items)];
}
