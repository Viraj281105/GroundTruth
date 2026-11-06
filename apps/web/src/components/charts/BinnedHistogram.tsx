import React from 'react';
import { compact, extent, linearScale, niceTicks } from './scale';
import styles from './extra.module.css';

export interface PreBin {
  from: number;
  to: number;
  count: number;
}

/** Histogram of pre-binned counts (the engine already binned the placebo effects) with a marked value. */
export function BinnedHistogram({ bins, marker, markerLabel, label }: { bins: PreBin[]; marker?: number; markerLabel?: string; label: string }) {
  const W = 360;
  const H = 160;
  const pad = { l: 28, r: 8, t: 16, b: 24 };
  const d = extent([...bins.flatMap((b) => [b.from, b.to]), ...(marker !== undefined ? [marker] : [])]);
  if (bins.length === 0 || !d) return <span className={styles.empty}>no distribution</span>;
  const x = linearScale(d, [pad.l, W - pad.r]);
  const top = Math.max(...bins.map((b) => b.count), 1);
  const y = linearScale({ min: 0, max: top }, [H - pad.b, pad.t]);
  const right = marker !== undefined && x(marker) > W / 2;
  return (
    <svg className={styles.svg} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {bins.map((b, i) => (
        <rect key={i} x={x(b.from) + 0.5} y={y(b.count)} width={Math.max(x(b.to) - x(b.from) - 1, 1)} height={H - pad.b - y(b.count)} fill="var(--neutral-text)" opacity="0.5" rx="1.5" />
      ))}
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className={styles.axis} />
      {niceTicks(d, 5).map((t) => (
        <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className={styles.tick}>
          {compact(t)}
        </text>
      ))}
      {marker !== undefined && Number.isFinite(marker) && (
        <g>
          <line x1={x(marker)} x2={x(marker)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--accent)" strokeWidth="2.5" />
          <text x={x(marker)} y={pad.t - 6} textAnchor={right ? 'end' : 'start'} dx={right ? -4 : 4} className={styles.mark}>
            {markerLabel ?? 'observed'}
          </text>
        </g>
      )}
    </svg>
  );
}
