import React from 'react';
import { compact, extent, linearScale } from './scale';
import styles from './extra.module.css';

export interface SignedBar {
  label: string;
  value: number;
  tone?: 'observed' | 'synthetic' | 'accent' | 'neutral';
}

const TONE = { observed: 'var(--series-observed)', synthetic: 'var(--series-synthetic)', accent: 'var(--accent)', neutral: 'var(--neutral-text)' };

/** Horizontal bars that diverge from a zero line, so signs and relative size can be compared. */
export function SignedBars({ items, label }: { items: SignedBar[]; label: string }) {
  const W = 360;
  const row = 34;
  const H = items.length * row + 10;
  const d = extent([...items.map((i) => i.value), 0]);
  if (items.length === 0 || !d) return <span className={styles.empty}>nothing to chart</span>;
  const x = linearScale(d, [110, W - 44]);
  return (
    <svg className={styles.svg} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <line x1={x(0)} x2={x(0)} y1="2" y2={H - 4} className={styles.zero} />
      {items.map((it, i) => {
        const yy = 8 + i * row;
        const x0 = x(0);
        const x1 = x(it.value);
        return (
          <g key={it.label}>
            <text x="0" y={yy + 13} className={styles.lbl}>
              {it.label}
            </text>
            <rect x={Math.min(x0, x1)} y={yy} width={Math.max(Math.abs(x1 - x0), 2)} height="18" rx="4" fill={TONE[it.tone ?? 'accent']} opacity="0.8" />
            <text x={x1 >= x0 ? x1 + 5 : x1 - 5} y={yy + 13} textAnchor={x1 >= x0 ? 'start' : 'end'} className={styles.tick}>
              {compact(it.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
