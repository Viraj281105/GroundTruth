'use client';

import React from 'react';
import { PlaceboDistributionData } from '../../lib/fixtures/simulated-data';
import { Badge } from '../ui/Badge';
import { sig } from '../../lib/evidence';
import { Info } from 'lucide-react';
import styles from './PlaceboDistribution.module.css';

export interface PlaceboDistributionProps {
  data: PlaceboDistributionData;
  className?: string;
}

export const PlaceboDistribution: React.FC<PlaceboDistributionProps> = ({
  data,
  className = '',
}) => {
  const { bins, projectStatistic, pValue, rank, totalUnits, significanceLevel, pValueFloor } = data;
  // Keep x labels legible at phone width however many bins there are.
  const tickEvery = Math.max(1, Math.ceil(bins.length / 8));
  const nPlacebos = bins.reduce((n, b) => n + b.count, 0);
  const belowAlpha = significanceLevel !== undefined && pValue <= significanceLevel;
  const pText = `p = ${sig(pValue)}`;
  const qualifierText = [
    pValueFloor !== undefined ? `floor ${sig(pValueFloor)}` : null,
    significanceLevel !== undefined ? `α = ${sig(significanceLevel)}` : null,
  ]
    .filter(Boolean)
    .join(', ');
  const chartDescription =
    `Histogram of the post/pre RMSPE ratio for ${nPlacebos} untreated placebo regions, ` +
    `ranging from ${sig(bins[0]?.min ?? 0)} to ${sig(bins[bins.length - 1]?.max ?? 0)}. ` +
    `The project's ratio is ${sig(projectStatistic)}, rank ${rank} of ${totalUnits} units; ` +
    `${pText}${qualifierText ? ` (${qualifierText})` : ''}.`;

  const maxCount = Math.max(...bins.map((b) => b.count), 1);
  const width = 600;
  const height = 240;
  const padLeft = 45;
  const padRight = 30;
  const padTop = 20;
  const padBottom = 40;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const minStat = bins[0]?.min ?? 0;
  const maxStat = bins[bins.length - 1]?.max ?? 5;

  const scaleX = (val: number) =>
    padLeft + ((val - minStat) / (maxStat - minStat)) * chartW;
  const scaleY = (count: number) =>
    padTop + chartH - (count / maxCount) * chartH;

  const projectX = scaleX(projectStatistic);

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h4 className={styles.title}>In-Space Placebo Permutation Distribution</h4>
          <Badge tone={belowAlpha ? 'positive' : 'inconclusive'} size="sm" variant="subtle">
            {pText}
            {qualifierText ? ` (${qualifierText})` : ''}
          </Badge>
          <Badge tone="neutral" size="sm" variant="outline">
            RANK: {rank} OF {totalUnits}
          </Badge>
        </div>
        <p className={styles.subtitle}>
          Evaluates whether the estimated gap could arise by chance among untreated comparison regions.
        </p>
      </div>

      {/* Histogram SVG */}
      <div className={styles.svgWrapper}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className={styles.svg}
          role="img"
          aria-label={chartDescription}
        >
          {/* Horizontal grid lines */}
          {[0, Math.ceil(maxCount / 2), maxCount].map((cnt) => {
            const y = scaleY(cnt);
            return (
              <g key={cnt}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={padLeft + chartW}
                  y2={y}
                  className={styles.gridLine}
                />
                <text x={padLeft - 8} y={y + 4} className={styles.tickY}>
                  {cnt}
                </text>
              </g>
            );
          })}

          {/* Histogram Bins */}
          {bins.map((b, i) => {
            const x1 = scaleX(b.min);
            const x2 = scaleX(b.max);
            const barW = Math.max(x2 - x1 - 2, 2);
            const barH = (b.count / maxCount) * chartH;
            const y = padTop + chartH - barH;
            const containsProject =
              projectStatistic >= b.min && projectStatistic < b.max;

            return (
              <g key={i}>
                <rect
                  x={x1 + 1}
                  y={y}
                  width={barW}
                  height={barH}
                  className={`${styles.bar} ${containsProject ? styles.barWithProject : ''}`}
                />
                {i % tickEvery === 0 && (
                  <text x={x1} y={padTop + chartH + 18} className={styles.tickX}>
                    {sig(b.min)}
                  </text>
                )}
              </g>
            );
          })}
          <text x={padLeft + chartW / 2} y={height - 4} className={styles.tickX}>
            Post/pre RMSPE ratio (×)
          </text>

          {/* Project Statistic Line */}
          <line
            x1={projectX}
            y1={padTop}
            x2={projectX}
            y2={padTop + chartH}
            className={styles.projectLine}
          />

          {/* Project Pin Marker */}
          <circle cx={projectX} cy={padTop + 6} r={5} className={styles.projectPin} />
          <text
            x={projectX}
            y={padTop - 6}
            className={styles.projectLabel}
            textAnchor="middle"
          >
            PROJECT ({sig(projectStatistic)}×)
          </text>
        </svg>
      </div>

      {/* Interpretation Alert Box */}
      <div className={styles.interpretationBox}>
        <Info size={16} className={styles.infoIcon} />
        <p className={styles.interpretationText}>
          <strong>Interpretation:</strong> The project&apos;s post/pre RMSPE ratio ranks{' '}
          <strong>
            {rank} of {totalUnits}
          </strong>{' '}
          units ({pText}
          {qualifierText ? `; ${qualifierText}` : ''}).{' '}
          {pValueFloor !== undefined && Math.abs(pValue - pValueFloor) < 1e-12
            ? `No placebo region diverges as much; with ${nPlacebos} placebos ${sig(pValueFloor)} is the smallest p-value this test can produce, not a p-value near zero.`
            : belowAlpha
              ? 'Few placebo regions diverge as much as the project.'
              : 'The divergence is within the range seen in placebo regions and is not distinguishable from them by this test.'}{' '}
          <em>
            This is the share of untreated comparison regions diverging at least as much; it is not a
            probability of misreporting.
          </em>
        </p>
      </div>
    </div>
  );
};
