'use client';

import React from 'react';
import { Evidence } from '../../lib/types';
import { sig } from '../../lib/evidence';
import {
  deriveSpecCurve,
  dimensionLabel,
  formatSignAgreement,
  formatSpecCurveMedian,
} from '../../lib/spec-curve';
import { Badge } from '../ui/Badge';
import styles from './SpecificationCurve.module.css';

export interface SpecificationCurveProps {
  items: Evidence[];
  onSelectEvidence: (item: Evidence) => void;
  className?: string;
}

const WIDTH = 600;
const HEIGHT = 220;
const PAD = { left: 64, right: 20, top: 20, bottom: 36 };

/**
 * Specification curve: every estimate the one-at-a-time sweep produced,
 * sorted, with the median and its sensitivity envelope.
 *
 * The centre is drawn the same size as every other point and only labelled,
 * because the engine does not privilege it. The table below the chart is the
 * text alternative and the route to each estimate's provenance.
 */
export const SpecificationCurve: React.FC<SpecificationCurveProps> = ({
  items,
  onSelectEvidence,
  className = '',
}) => {
  const curve = deriveSpecCurve(items);

  if (!curve) {
    return (
      <section className={`${styles.container} ${className}`} aria-labelledby="spec-curve-title">
        <h4 id="spec-curve-title" className={styles.title}>
          Specification curve
        </h4>
        <p className={styles.empty}>
          Not measured. The specification curve was not run for this analysis, so the estimate has
          not been tested against alternative analytic choices here.
        </p>
      </section>
    );
  }

  const { estimates, range, unit, median } = curve;
  const values = estimates.map((e) => e.value);
  let lo = Math.min(...values, range?.lower ?? median);
  let hi = Math.max(...values, range?.upper ?? median);
  // Draw zero only when the sign is in question; otherwise it would flatten
  // the spread the curve exists to show, and the text says where zero is.
  if (curve.signFlips.length > 0) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  const span = Math.max(hi - lo, Math.abs(median) * 0.05, 1e-9);
  lo -= span * 0.15;
  hi += span * 0.15;

  const chartW = WIDTH - PAD.left - PAD.right;
  const chartH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) =>
    PAD.left + (estimates.length === 1 ? chartW / 2 : (i / (estimates.length - 1)) * chartW);
  const y = (v: number) => PAD.top + chartH - ((v - lo) / (hi - lo)) * chartH;
  const ticks = [lo + (hi - lo) * 0.15, (lo + hi) / 2, hi - (hi - lo) * 0.15];
  const zeroVisible = lo <= 0 && hi >= 0;

  const chartDescription =
    `Specification curve of ${estimates.length} estimates in ${unit}, sorted from ` +
    `${sig(values[0])} to ${sig(values[values.length - 1])}. Median ${sig(median)} ${unit}. ` +
    (curve.signFlips.length === 0
      ? 'All estimates share the median’s sign.'
      : `${curve.signFlips.length} estimates have the opposite sign.`) +
    ' The full list is in the table below.';

  return (
    <section className={`${styles.container} ${className}`} aria-labelledby="spec-curve-title">
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h4 id="spec-curve-title" className={styles.title}>
            Specification curve
          </h4>
          <Badge tone={curve.tone} size="sm" variant="subtle">
            {curve.status}
          </Badge>
        </div>
        <p className={styles.subtitle}>
          The estimate re-run with one analytic choice changed at a time. The centre is the
          request&apos;s own specification; it is marked, not privileged.
        </p>
      </div>

      <dl className={styles.facts}>
        <div className={styles.fact}>
          <dt>Median across specifications</dt>
          <dd>
            <button
              type="button"
              className={styles.factButton}
              onClick={() => onSelectEvidence(curve.medianItem)}
              aria-label={`Median across specifications: ${formatSpecCurveMedian(curve)}. Show provenance.`}
            >
              {formatSpecCurveMedian(curve)}
            </button>
          </dd>
        </div>
        <div className={styles.fact}>
          <dt>Agree with the median&apos;s sign</dt>
          <dd>
            {curve.signAgreementItem ? (
              <button
                type="button"
                className={styles.factButton}
                onClick={() => curve.signAgreementItem && onSelectEvidence(curve.signAgreementItem)}
                aria-label={`Agree with the median's sign: ${formatSignAgreement(curve)}. Show provenance.`}
              >
                {formatSignAgreement(curve)}
              </button>
            ) : (
              formatSignAgreement(curve)
            )}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt>Choices varied in this run</dt>
          <dd>{curve.dimensionsVaried.map(dimensionLabel).join(', ') || 'None reported'}</dd>
        </div>
        <div className={styles.fact}>
          <dt>Not varied in this run</dt>
          <dd>
            {curve.dimensionsNotVaried.length > 0
              ? `${curve.dimensionsNotVaried.map(dimensionLabel).join(', ')} (need new data or re-matching)`
              : 'None reported'}
          </dd>
        </div>
      </dl>

      <p className={styles.summary}>{curve.summary}</p>
      {curve.nFailed > 0 && (
        <p className={styles.summary}>
          {curve.nFailed} specification{curve.nFailed === 1 ? '' : 's'} could not be estimated and{' '}
          {curve.nFailed === 1 ? 'is' : 'are'} absent from the curve; see the run warnings for reasons.
        </p>
      )}

      <div className={styles.svgWrapper}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.svg} role="img" aria-label={chartDescription}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(t)} y2={y(t)} className={styles.gridLine} />
              <text x={PAD.left - 8} y={y(t) + 4} className={styles.tickY}>
                {sig(t)}
              </text>
            </g>
          ))}
          {range && (
            <rect
              x={PAD.left}
              y={y(range.upper)}
              width={chartW}
              height={Math.max(y(range.lower) - y(range.upper), 1)}
              className={styles.envelope}
            />
          )}
          {zeroVisible && (
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(0)} y2={y(0)} className={styles.zeroLine} />
          )}
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(median)} y2={y(median)} className={styles.medianLine} />
          <text x={WIDTH - PAD.right} y={y(median) - 6} className={styles.medianLabel} textAnchor="end">
            median
          </text>
          {estimates.map((e, i) =>
            e.flipsSign ? (
              <path
                key={e.specId}
                d={`M ${x(i)} ${y(e.value) - 6} L ${x(i) + 6} ${y(e.value) + 5} L ${x(i) - 6} ${y(e.value) + 5} Z`}
                className={styles.flipPoint}
              />
            ) : (
              <circle key={e.specId} cx={x(i)} cy={y(e.value)} r={5} className={styles.point} />
            ),
          )}
          {estimates.map((e, i) =>
            e.isCentre ? (
              <g key={`${e.specId}-label`}>
                <circle cx={x(i)} cy={y(e.value)} r={9} className={styles.centreRing} />
                <text x={x(i)} y={y(e.value) - 14} className={styles.centreLabel} textAnchor="middle">
                  centre
                </text>
              </g>
            ) : null,
          )}
          <text x={PAD.left + chartW / 2} y={HEIGHT - 8} className={styles.axisLabel} textAnchor="middle">
            Specifications, sorted by estimate
          </text>
          <text
            x={14}
            y={PAD.top + chartH / 2}
            className={styles.axisLabel}
            textAnchor="middle"
            transform={`rotate(-90 14 ${PAD.top + chartH / 2})`}
          >
            Effect ({unit})
          </text>
        </svg>
      </div>
      {!zeroVisible && (
        <p className={styles.note}>
          Zero lies {median > 0 ? 'below' : 'above'} the plotted range: every estimate is{' '}
          {median > 0 ? 'positive' : 'negative'}. Shaded band: the sensitivity envelope (smallest to
          largest estimate).
        </p>
      )}

      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <caption className={styles.caption}>
            Every specification, sorted by estimate. Select an estimate for its provenance.
          </caption>
          <thead>
            <tr>
              <th scope="col">Specification</th>
              <th scope="col" className={styles.dimensionCol}>
                Choice varied
              </th>
              <th scope="col">Estimate</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {estimates.map((e) => (
              <tr key={e.specId}>
                <th scope="row">{e.label}</th>
                <td className={styles.dimensionCol}>{dimensionLabel(e.dimension)}</td>
                <td>
                  <button
                    type="button"
                    className={styles.cellButton}
                    onClick={() => onSelectEvidence(e.item)}
                    aria-label={`${e.label}: ${sig(e.value)} ${unit}. Show provenance.`}
                  >
                    {sig(e.value)} {unit}
                  </button>
                </td>
                <td>
                  {[e.isCentre ? 'Centre (not privileged)' : null, e.flipsSign ? 'Opposite sign to median' : null]
                    .filter(Boolean)
                    .join('; ') || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
