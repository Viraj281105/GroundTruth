import React from 'react';
import { compact, extent, linearScale, niceTicks } from './scale';
import styles from './extra.module.css';

export interface SpecDot {
  value: number;
  /** The main specification. */
  main?: boolean;
  flipsSign?: boolean;
}

/** Every specification as one point, ordered by estimate, with a zero line and the main one highlighted. */
export function SpecDots({ dots, label, unit = '' }: { dots: SpecDot[]; label: string; unit?: string }) {
  const W = 360;
  const H = 190;
  const pad = { l: 42, r: 10, t: 16, b: 20 };
  const d = extent([...dots.map((s) => s.value), 0]);
  if (dots.length === 0 || !d) return <span className={styles.empty}>no specifications</span>;
  const sorted = [...dots].sort((a, b) => a.value - b.value);
  const x = linearScale({ min: 0, max: Math.max(sorted.length - 1, 1) }, [pad.l + 6, W - pad.r - 6]);
  const y = linearScale(d, [H - pad.b, pad.t]);
  return (
    <svg className={styles.svg} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {niceTicks(d, 5).map((t) => (
        <text key={t} x={pad.l - 6} y={y(t) + 3} textAnchor="end" className={styles.tick}>
          {compact(t)}
        </text>
      ))}
      <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} className={styles.zero} />
      <text x={W - pad.r} y={y(0) - 4} textAnchor="end" className={styles.tick}>
        zero{unit ? ` (${unit})` : ''}
      </text>
      {sorted.map((s, i) => (
        <circle key={i} cx={x(i)} cy={y(s.value)} r={s.main ? 7 : 4.5} fill={s.main ? 'var(--accent)' : s.flipsSign ? 'var(--caution-text)' : 'var(--neutral-text)'} opacity={s.main ? 1 : 0.7} stroke="var(--surface-raised)" strokeWidth="1.5" />
      ))}
    </svg>
  );
}
