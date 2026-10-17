import { Evidence } from './types';
import { DiagnosticGroup, row } from './diagnostics';
import { formatConfidenceInterval } from './formatters';
import { NOT_MEASURED, findEvidence, sig, withUnit } from './evidence';

/**
 * Display model for the difference-in-differences cross-check and its
 * cluster-robust inference (engine PR #71).
 *
 * The bootstrap interval is attached to the standard-error item but brackets
 * the DiD estimate, so it is shown with the estimate. The two inference
 * limitations — control-side only, and independent units when no cluster
 * labels exist — are caveats that travel with the numbers and are always
 * shown.
 */

function stringParam(item: Evidence | undefined, key: string): string | undefined {
  const v = item?.provenance.parameters?.[key];
  return typeof v === 'string' ? v : undefined;
}

function numberParam(item: Evidence | undefined, key: string): number | undefined {
  const v = item?.provenance.parameters?.[key];
  return typeof v === 'number' ? v : undefined;
}

export function didEstimateGroup(items: Evidence[]): DiagnosticGroup {
  const estimate = findEvidence(items, 'crosscheck.did_estimate');
  const se = findEvidence(items, 'crosscheck.did_standard_error');
  const plausible = estimate?.qualifiers?.parallel_trends_plausible;
  const scm = findEvidence(items, 'effect.point_estimate');

  let status = NOT_MEASURED;
  let tone: DiagnosticGroup['tone'] = 'neutral';
  let summary = 'The difference-in-differences cross-check was not run for this analysis.';
  if (estimate) {
    if (plausible === true) {
      status = 'PARALLEL TRENDS PLAUSIBLE';
      tone = 'positive';
      summary =
        'The project and its controls drifted similarly before treatment, so the cross-check is informative. Agreement or disagreement with the synthetic control is part of the finding.';
    } else if (plausible === false) {
      status = 'PARALLEL TRENDS FAIL';
      tone = 'caution';
      summary =
        'The pre-treatment drift between the project and its controls could explain much of this estimate on its own, so the cross-check is uninformative here; rely on the synthetic control.';
    } else {
      status = 'SCREEN NOT REPORTED';
    }
  }

  return {
    id: 'did-estimate',
    title: 'Difference-in-differences cross-check',
    summary,
    status,
    tone,
    rows: [
      row(
        items,
        'crosscheck.did_estimate',
        'DiD estimate',
        (i) => withUnit(i),
        () => (se?.confidence ? formatConfidenceInterval(se.confidence, se.unit) : 'No interval reported'),
      ),
      row(
        items,
        'crosscheck.did_pre_trend_divergence',
        'Pre-treatment slope divergence',
        (i) => withUnit(i),
        () => 'Project minus controls, per period',
      ),
      row(
        items,
        'effect.point_estimate',
        'Synthetic-control estimate, for comparison',
        () => (scm ? withUnit(scm) : NOT_MEASURED),
        () => 'Primary estimator',
      ),
    ],
  };
}

export function didInferenceGroup(items: Evidence[]): DiagnosticGroup {
  const se = findEvidence(items, 'crosscheck.did_standard_error');
  const q = se?.qualifiers ?? {};
  const clusterLevel = typeof q.cluster_level === 'string' ? q.cluster_level : undefined;
  const nClusters = typeof q.n_clusters === 'number' ? q.n_clusters : undefined;
  const bootSe = typeof q.bootstrap_standard_error === 'number' ? q.bootstrap_standard_error : undefined;
  const weights = stringParam(se, 'bootstrap_weights');
  const nBoot = numberParam(se, 'n_bootstrap');

  const caveats: string[] = [];
  if (se) {
    if (q.control_side_only !== false) {
      caveats.push(
        'Control-side uncertainty only: with one treated unit its own noise cannot be estimated, so this understates the full uncertainty.',
      );
    }
    if (q.independent_units_assumed === true) {
      caveats.push(
        'No cluster labels were available, so each control region is treated as an independent draw, which understates the uncertainty further.',
      );
    }
  }

  const bootDetail = [
    bootSe !== undefined && se ? `Bootstrap SE ${sig(bootSe)} ${se.unit}`.trim() : null,
    weights ? `${weights} weights` : null,
    nBoot !== undefined ? `${nBoot} draws` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return {
    id: 'did-inference',
    title: 'Cross-check inference',
    summary: se
      ? 'Cluster-robust (CR1) standard error with a wild cluster bootstrap interval. Read both against the caveats below.'
      : 'Cluster-robust inference was not reported for this cross-check.',
    status: se ? (q.independent_units_assumed === true ? 'UNITS ASSUMED INDEPENDENT' : 'CLUSTERED') : NOT_MEASURED,
    tone: 'neutral',
    caveats,
    rows: [
      row(
        items,
        'crosscheck.did_standard_error',
        'Cluster-robust standard error (CR1)',
        (i) => withUnit(i),
        () =>
          [clusterLevel ? `Clustered by ${clusterLevel}` : null, nClusters !== undefined ? `${nClusters} clusters` : null]
            .filter(Boolean)
            .join(' · ') || undefined,
      ),
      row(
        items,
        'crosscheck.did_standard_error',
        'Wild cluster bootstrap',
        (i) => (i.confidence ? formatConfidenceInterval(i.confidence, i.unit) : 'No interval reported'),
        () => bootDetail || undefined,
      ),
    ],
  };
}

export function deriveDidDiagnostics(items: Evidence[]): DiagnosticGroup[] {
  return [didEstimateGroup(items), didInferenceGroup(items)];
}
