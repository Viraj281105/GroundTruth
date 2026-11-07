'use client';

import React, { useMemo, useState } from 'react';
import { sig } from '../../../lib/evidence';
import { dimensionLabel, type SpecCurve, type SpecEstimate } from '../../../lib/spec-curve';
import { Term } from '../evidence/Term';
import { NO_FILTER, countByDimension, dimensionsOf, filterSpecs, type SpecFilter } from './spec-filter';
import styles from './robustness.module.css';

const W = 640;
const H = 240;
const PAD = { l: 56, r: 16, t: 16, b: 28 };

export function Multiverse({ curve, onSelect }: { curve: SpecCurve; onSelect: (s: SpecEstimate) => void }) {
  const [filter, setFilter] = useState<SpecFilter>(NO_FILTER);
  const [active, setActive] = useState<SpecEstimate | null>(null);

  const all = curve.estimates;
  const dims = useMemo(() => dimensionsOf(all), [all]);
  const counts = useMemo(() => countByDimension(all), [all]);
  const shown = useMemo(() => filterSpecs(all, filter), [all, filter]);

  const values = all.map((s) => s.value);
  let lo = Math.min(...values, curve.range?.lower ?? curve.median);
  let hi = Math.max(...values, curve.range?.upper ?? curve.median);
  if (curve.signFlips.length > 0) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  const span = Math.max(hi - lo, Math.abs(curve.median) * 0.05, 1e-9);
  lo -= span * 0.12;
  hi += span * 0.12;
  const cw = W - PAD.l - PAD.r;
  const ch = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (shown.length <= 1 ? cw / 2 : (i / (shown.length - 1)) * cw);
  const y = (v: number) => PAD.t + ch - ((v - lo) / (hi - lo)) * ch;
  const ticks = [lo + span * 0.12, (lo + hi) / 2, hi - span * 0.12];

  const detail = active ?? null;

  return (
    <div className={styles.multiverse}>
      <div className={styles.filters} role="group" aria-label="Filter by analytic choice">
        <button
          type="button"
          className={styles.chip}
          aria-pressed={filter.dimension === null}
          onClick={() => setFilter((f) => ({ ...f, dimension: null }))}
        >
          All choices ({all.length})
        </button>
        {dims.map((d) => (
          <button
            key={d}
            type="button"
            className={styles.chip}
            aria-pressed={filter.dimension === d}
            onClick={() => setFilter((f) => ({ ...f, dimension: f.dimension === d ? null : d }))}
          >
            {dimensionLabel(d)} ({counts[d]})
          </button>
        ))}
        {curve.signFlips.length > 0 && (
          <button
            type="button"
            className={styles.chip}
            aria-pressed={filter.flipsOnly}
            onClick={() => setFilter((f) => ({ ...f, flipsOnly: !f.flipsOnly }))}
          >
            Opposite sign only ({curve.signFlips.length})
          </button>
        )}
      </div>

      {shown.length === 0 ? (
        <p className={styles.empty}>No specification matches this filter.</p>
      ) : (
        <div className={styles.chartBox}>
          <svg viewBox={`0 0 ${W} ${H}`} className={styles.svg} role="group" aria-label={`Multiverse of ${shown.length} specifications`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className={styles.grid} />
                <text x={PAD.l - 8} y={y(t)} className={styles.tick} textAnchor="end" dominantBaseline="middle">
                  {sig(t)}
                </text>
              </g>
            ))}
            {lo <= 0 && hi >= 0 && <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className={styles.zero} />}
            <line x1={PAD.l} x2={W - PAD.r} y1={y(curve.median)} y2={y(curve.median)} className={styles.median} />
            {shown.map((s, i) => {
              const on = active?.specId === s.specId;
              return (
                <circle
                  key={s.specId}
                  cx={x(i)}
                  cy={y(s.value)}
                  r={on ? 8 : s.isCentre ? 7 : 5.5}
                  className={`${styles.pt} ${s.flipsSign ? styles.flip : ''} ${s.isCentre ? styles.centre : ''}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${s.label}: ${sig(s.value)} ${curve.unit}${s.flipsSign ? ', opposite sign to the median' : ''}`}
                  onMouseEnter={() => setActive(s)}
                  onFocus={() => setActive(s)}
                  onClick={() => onSelect(s)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(s);
                    }
                  }}
                />
              );
            })}
          </svg>
        </div>
      )}

      <div className={styles.readout} aria-live="polite">
        {detail ? (
          <>
            <strong>{detail.label}</strong>
            <span>
              {sig(detail.value)} {curve.unit} · {dimensionLabel(detail.dimension)}
              {detail.flipsSign ? ' · opposite sign to the median' : ''}
            </span>
          </>
        ) : (
          <span className={styles.muted}>
            Hover or focus a point to see its specification. The dashed line is the <Term id="spec-curve">median</Term> of all {curve.nSpecifications}{' '}
            specifications ({sig(curve.median)} {curve.unit}).
          </span>
        )}
      </div>
    </div>
  );
}
