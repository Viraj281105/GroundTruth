import React from 'react';
import { compact, extent, histogram, linePath, linearScale, niceTicks } from './scale';
import styles from './charts.module.css';

export type Tone = 'observed' | 'synthetic' | 'accent' | 'caution' | 'neutral' | 'danger';
const TONE_VAR: Record<Tone, string> = {
  observed: 'var(--series-observed)',
  synthetic: 'var(--series-synthetic)',
  accent: 'var(--accent)',
  caution: 'var(--caution-text)',
  neutral: 'var(--neutral-text)',
  danger: 'var(--danger-text)',
};

interface Labelled {
  /** Spoken description of the whole chart for screen readers. */
  label: string;
}

/* ---------------------------------------------------------------- Sparkline */

export function Sparkline({ values, label, tone = 'accent', height = 36, fill = true }: Labelled & { values: number[]; tone?: Tone; height?: number; fill?: boolean }) {
  const W = 120;
  const d = extent(values);
  if (!d || values.length < 2) return <span className={styles.empty}>no series</span>;
  const x = linearScale({ min: 0, max: values.length - 1 }, [2, W - 2]);
  const y = linearScale(d, [height - 3, 3]);
  const pts = values.map((v, i) => ({ x: x(i), y: y(v) }));
  const line = linePath(pts);
  return (
    <svg className={styles.spark} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ height }}>
      {fill && <path d={`${line}L${W - 2} ${height}L2 ${height}Z`} fill={TONE_VAR[tone]} opacity="0.12" />}
      <path d={line} fill="none" stroke={TONE_VAR[tone]} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/* ------------------------------------------------------------------ BarList */

export interface BarItem {
  label: string;
  value: number;
  tone?: Tone;
  /** Shown instead of the number, e.g. "34%". */
  display?: string;
}

/** Horizontal bars with the value at the end. Negative values are not drawn as bars. */
export function BarList({ items, label, max }: Labelled & { items: BarItem[]; max?: number }) {
  const top = max ?? Math.max(...items.map((i) => (Number.isFinite(i.value) ? i.value : 0)), 0);
  if (items.length === 0 || top <= 0) return <span className={styles.empty}>nothing to chart</span>;
  return (
    <ul className={styles.bars} role="img" aria-label={label}>
      {items.map((item) => {
        const pct = Number.isFinite(item.value) ? Math.max(0, Math.min(100, (item.value / top) * 100)) : 0;
        return (
          <li key={item.label} className={styles.barRow}>
            <span className={styles.barLabel}>{item.label}</span>
            <span className={styles.barTrack}>
              <span className={styles.barFill} style={{ width: `${pct}%`, background: TONE_VAR[item.tone ?? 'accent'] }} />
            </span>
            <span className={`${styles.barValue} num`}>{item.display ?? compact(item.value)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/* ---------------------------------------------------------------- Histogram */

/** Distribution with an optional marked value (e.g. the observed effect among placebo effects). */
export function HistogramChart({ values, marker, markerLabel, label, bins = 14, tone = 'neutral' }: Labelled & { values: number[]; marker?: number; markerLabel?: string; bins?: number; tone?: Tone }) {
  const W = 360;
  const H = 150;
  const pad = { l: 28, r: 8, t: 12, b: 24 };
  const hist = histogram(values, bins);
  const d = extent([...values, ...(marker !== undefined ? [marker] : [])]);
  if (hist.length === 0 || !d) return <span className={styles.empty}>no distribution</span>;
  const x = linearScale(d, [pad.l, W - pad.r]);
  const topCount = Math.max(...hist.map((b) => b.count), 1);
  const y = linearScale({ min: 0, max: topCount }, [H - pad.b, pad.t]);
  const ticks = niceTicks(d, 5);
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {hist.map((b, i) => (
        <rect key={i} x={x(b.from) + 0.5} y={y(b.count)} width={Math.max(x(b.to) - x(b.from) - 1, 1)} height={H - pad.b - y(b.count)} fill={TONE_VAR[tone]} opacity="0.55" rx="1.5" />
      ))}
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className={styles.axis} />
      {ticks.map((t) => (
        <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className={styles.tick}>
          {compact(t)}
        </text>
      ))}
      {marker !== undefined && Number.isFinite(marker) && (
        <g>
          <line x1={x(marker)} x2={x(marker)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--accent)" strokeWidth="2" />
          <text x={Math.min(x(marker) + 5, W - 40)} y={pad.t + 4} className={styles.markerText}>
            {markerLabel ?? 'observed'}
          </text>
        </g>
      )}
    </svg>
  );
}

/* ----------------------------------------------------------------- RangeBar */

/** A point estimate with its interval on a number line, with a zero reference. */
export function RangeBar({ estimate, low, high, label, unit = '' }: Labelled & { estimate: number; low: number; high: number; unit?: string }) {
  const W = 360;
  const H = 70;
  if (![estimate, low, high].every(Number.isFinite)) return <span className={styles.empty}>no interval</span>;
  const lo = Math.min(low, 0, estimate);
  const hi = Math.max(high, 0, estimate);
  const span = (hi - lo) * 0.12 || 1;
  const x = linearScale({ min: lo - span, max: hi + span }, [10, W - 10]);
  const ticks = niceTicks({ min: lo - span, max: hi + span }, 5);
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <line x1="10" x2={W - 10} y1="34" y2="34" className={styles.axis} />
      {ticks.map((t) => (
        <text key={t} x={x(t)} y={H - 6} textAnchor="middle" className={styles.tick}>
          {compact(t)}
        </text>
      ))}
      <line x1={x(0)} x2={x(0)} y1="14" y2="54" stroke="var(--border-strong)" strokeDasharray="3 3" />
      <rect x={x(low)} y="28" width={Math.max(x(high) - x(low), 2)} height="12" rx="6" fill="var(--accent)" opacity="0.25" />
      <line x1={x(low)} x2={x(low)} y1="26" y2="42" stroke="var(--accent)" strokeWidth="2" />
      <line x1={x(high)} x2={x(high)} y1="26" y2="42" stroke="var(--accent)" strokeWidth="2" />
      <circle cx={x(estimate)} cy="34" r="6.5" fill="var(--accent)" stroke="var(--surface-raised)" strokeWidth="2" />
      <text x={x(estimate)} y="18" textAnchor="middle" className={styles.markerText}>
        {compact(estimate)}
        {unit}
      </text>
    </svg>
  );
}

/* -------------------------------------------------------------------- Donut */

export function Donut({ value, max = 1, label, caption, tone = 'accent', size = 112 }: Labelled & { value: number; max?: number; caption?: string; tone?: Tone; size?: number }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const frac = Number.isFinite(value) && max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <figure className={styles.donut} style={{ width: size }}>
      <svg viewBox="0 0 100 100" role="img" aria-label={label}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--border-subtle)" strokeWidth="9" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={TONE_VAR[tone]} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${frac * c} ${c}`} transform="rotate(-90 50 50)" />
        <text x="50" y="55" textAnchor="middle" className={styles.donutValue}>
          {Number.isFinite(value) ? compact(value) : '–'}
        </text>
      </svg>
      {caption && <figcaption className={styles.donutCaption}>{caption}</figcaption>}
    </figure>
  );
}

/* ---------------------------------------------------------------- LineChart */

export interface LineSeries {
  name: string;
  tone: Tone;
  points: Array<{ x: number; y: number }>;
  dashed?: boolean;
}

/** Multi-series line chart on shared axes. An optional vertical reference marks an event such as the intervention. */
export function LineChart({ series, label, refX, refLabel, height = 220 }: Labelled & { series: LineSeries[]; refX?: number; refLabel?: string; height?: number }) {
  const W = 520;
  const pad = { l: 40, r: 12, t: 14, b: 26 };
  const all = series.flatMap((s) => s.points);
  const xd = extent(all.map((p) => p.x));
  const yd = extent(all.map((p) => p.y));
  if (!xd || !yd) return <span className={styles.empty}>no series</span>;
  const x = linearScale(xd, [pad.l, W - pad.r]);
  const y = linearScale(yd, [height - pad.b, pad.t]);
  const xt = niceTicks(xd, 6);
  const yt = niceTicks(yd, 5);
  return (
    <figure className={styles.lineFigure}>
      <svg className={styles.chart} viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        {yt.map((t) => (
          <g key={`y${t}`}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={styles.grid} />
            <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" className={styles.tick}>
              {compact(t)}
            </text>
          </g>
        ))}
        {xt.map((t) => (
          <text key={`x${t}`} x={x(t)} y={height - 8} textAnchor="middle" className={styles.tick}>
            {t}
          </text>
        ))}
        {refX !== undefined && (
          <g>
            <line x1={x(refX)} x2={x(refX)} y1={pad.t} y2={height - pad.b} stroke="var(--border-strong)" strokeDasharray="4 4" />
            {refLabel && (
              <text x={x(refX) + 5} y={pad.t + 8} className={styles.tick}>
                {refLabel}
              </text>
            )}
          </g>
        )}
        {series.map((s) => (
          <path key={s.name} d={linePath(s.points.map((p) => ({ x: x(p.x), y: y(p.y) })))} fill="none" stroke={TONE_VAR[s.tone]} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={s.dashed ? '5 4' : undefined} />
        ))}
      </svg>
      <figcaption className={styles.legend}>
        {series.map((s) => (
          <span key={s.name} className={styles.legendItem}>
            <i style={{ background: TONE_VAR[s.tone] }} />
            {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
