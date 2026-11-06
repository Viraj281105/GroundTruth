import React from 'react';
import type { StageSummary } from './model';
import styles from './method.module.css';

/** Evidence ladder: one rung per pipeline stage, bar length proportional to evidence items produced. */
export function PipelineLadder({ stages }: { stages: StageSummary[] }) {
  if (stages.length === 0) return null;
  const W = 360;
  const ROW = 46;
  const H = stages.length * ROW + 6;
  const maxItems = Math.max(...stages.map((s) => s.items), 1);
  return (
    <svg className={styles.ladder} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Evidence ladder: ${stages.length} stages, from ${stages[0].stage} to ${stages[stages.length - 1].stage}`}>
      <line x1="22" x2="22" y1="20" y2={H - 26} stroke="var(--border-strong)" strokeWidth="2" />
      {stages.map((s, i) => {
        const y = 4 + i * ROW;
        const w = Math.max((s.items / maxItems) * 150, 6);
        return (
          <g key={s.stage}>
            <circle cx="22" cy={y + 20} r="11" fill="var(--accent)" />
            <text x="22" y={y + 24} textAnchor="middle" className={styles.ladderNum}>
              {i + 1}
            </text>
            <text x="44" y={y + 14} className={styles.ladderLabel}>
              {s.stage}
            </text>
            <rect x="44" y={y + 20} width={w} height="10" rx="5" fill="var(--accent)" opacity="0.35" />
            <text x={44 + w + 8} y={y + 29} className={styles.ladderCount}>
              {s.items} {s.items === 1 ? 'item' : 'items'}, {s.methods} {s.methods === 1 ? 'method' : 'methods'}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
