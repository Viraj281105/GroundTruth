'use client';

import React, { useState } from 'react';
import { Card, EvidenceStateBadge, UnavailablePanel } from '../ds';
import { extent, linearScale, niceTicks, compact } from '../charts';
import { formatIndexValue } from './format';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { seriesPoints, type SeriesPoint } from './series.model';
import { isUnavailable, type ObservationsView } from './types';
import styles from './panels.module.css';

type Indicator = ObservationsView['indicator'];
const INDICATORS: { key: Indicator; label: string }[] = [
  { key: 'ndvi', label: 'NDVI' },
  { key: 'evi', label: 'EVI' },
  { key: 'ndmi', label: 'NDMI' },
  { key: 'nbr', label: 'NBR' },
];

const W = 520;
const H = 220;
const PAD = { l: 44, r: 14, t: 14, b: 28 };

/** Dots joined only between consecutive years; gap years get a dashed hollow marker and no line. */
function SeriesChart({ points, gaps, label }: { points: SeriesPoint[]; gaps: number[]; label: string }) {
  const xd = extent([...points.map((p) => p.year), ...gaps]);
  const yd = extent(points.map((p) => p.value));
  if (!xd || !yd) return <p className={styles.notice}>No observed points to chart.</p>;
  const pad = (yd.max - yd.min || Math.abs(yd.max) || 1) * 0.15;
  const yDom = { min: yd.min - pad, max: yd.max + pad };
  const x = linearScale(xd.min === xd.max ? { min: xd.min - 1, max: xd.max + 1 } : xd, [PAD.l, W - PAD.r]);
  const y = linearScale(yDom, [H - PAD.b, PAD.t]);
  const years: number[] = [];
  for (let yr = xd.min; yr <= xd.max; yr++) years.push(yr);
  const segs: string[] = [];
  let run: string[] = [];
  points.forEach((p, i) => {
    run.push(`${x(p.year)},${y(p.value)}`);
    const next = points[i + 1];
    if (!next || next.year !== p.year + 1) {
      if (run.length > 1) segs.push(run.join(' '));
      run = [];
    }
  });
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} data-chart="series">
      {niceTicks(yDom, 5).map((t) => (
        <g key={`y${t}`}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className={styles.grid} />
          <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" className={styles.tick}>
            {compact(t)}
          </text>
        </g>
      ))}
      <text x={4} y={10} className={styles.tick}>index value</text>
      {years.filter((_, i) => i % Math.ceil(years.length / 10) === 0).map((yr) => (
        <text key={`x${yr}`} x={x(yr)} y={H - 8} textAnchor="middle" className={styles.tick}>
          {yr}
        </text>
      ))}
      {segs.map((s) => (
        <polyline key={s} points={s} className={styles.line} />
      ))}
      {gaps.map((g) => (
        <circle key={`g${g}`} cx={x(g)} cy={H - PAD.b - 8} r={5} className={styles.gapMark} data-gap-year={g}>
          <title>{`No observation for ${g}`}</title>
        </circle>
      ))}
      {points.map((p) =>
        p.evidenceState === 'MODEL_ESTIMATED' ? (
          <rect key={p.year} x={x(p.year) - 4.5} y={y(p.value) - 4.5} width={9} height={9} transform={`rotate(45 ${x(p.year)} ${y(p.value)})`} className={styles.dotModel}>
            <title>{`${p.year}: ${formatIndexValue(p.value)} (model estimated)`}</title>
          </rect>
        ) : (
          <circle key={p.year} cx={x(p.year)} cy={y(p.value)} r={4.5} className={styles.dot}>
            <title>{`${p.year}: ${formatIndexValue(p.value)} (${p.evidenceState.toLowerCase()})`}</title>
          </circle>
        ),
      )}
    </svg>
  );
}

function SeriesTable({ points }: { points: SeriesPoint[] }) {
  const withScenes = points.some((p) => p.sceneIds !== null);
  return (
    <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Observed values by year, scrollable">
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Year</th>
            <th>Value</th>
            <th>Evidence state</th>
            <th>Sensor</th>
            <th>AOI coverage</th>
            <th>Scenes</th>
            {withScenes && <th>Scene ids</th>}
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.year}>
              <td className={styles.num}>{p.year}</td>
              <td className={styles.numcell} title={String(p.value)}>{formatIndexValue(p.value)}</td>
              <td>
                <EvidenceStateBadge state={p.evidenceState} />
              </td>
              <td>{p.sensor}</td>
              <td className={styles.numcell}>{p.aoiCoveragePct === null ? 'not computed' : `${p.aoiCoveragePct}%`}</td>
              <td className={styles.numcell}>{p.nScenes ?? '-'}</td>
              {withScenes && <td className={styles.mono}>{p.sceneIds ? p.sceneIds.join(', ') : ''}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface IndexSeriesPanelProps {
  /** One payload per indicator that has been fetched. */
  series?: ObservationsView[] | null;
  loading?: boolean;
  initialIndicator?: Indicator;
  initialView?: 'chart' | 'table';
}

export function IndexSeriesPanel({ series, loading, initialIndicator, initialView = 'chart' }: IndexSeriesPanelProps) {
  const first = series?.[0]?.indicator ?? 'ndvi';
  const [indicator, setIndicator] = useState<Indicator>(initialIndicator ?? first);
  const [view, setView] = useState<'chart' | 'table'>(initialView);
  if (loading) return <PanelLoading label="index series" />;
  if (!series || series.length === 0) return <PanelEmpty title="No index series" body="Vegetation index series appear once observations are ingested." />;
  const current = series.find((s) => s.indicator === indicator);
  const label = INDICATORS.find((i) => i.key === indicator)?.label ?? indicator;
  const { points, gaps } = current ? seriesPoints(current) : { points: [], gaps: [] };
  const coverage = points.map((p) => p.aoiCoveragePct).filter((v): v is number => v !== null);
  return (
    <Card className={styles.panel} aria-label="Vegetation index series">
      <div className={styles.head}>
        <h3 className={styles.title}>Vegetation index series</h3>
        <div className={styles.row}>
          <div className={styles.toggle} role="group" aria-label="Index">
            {INDICATORS.map((i) => (
              <button key={i.key} type="button" aria-pressed={i.key === indicator} onClick={() => setIndicator(i.key)}>
                {i.label}
              </button>
            ))}
          </div>
          <div className={styles.toggle} role="group" aria-label="View">
            {(['chart', 'table'] as const).map((v) => (
              <button key={v} type="button" aria-pressed={v === view} data-view={v} onClick={() => setView(v)}>
                {v === 'chart' ? 'Chart' : 'Table'}
              </button>
            ))}
          </div>
        </div>
      </div>
      {!current ? (
        <UnavailablePanel title={`${label} series`} reason={`No ${label} series was provided for this project.`} evidenceNeeded={`A completed observation ingest that includes ${label}.`} />
      ) : isUnavailable(current) ? (
        <UnavailablePanel title={`${label} series`} reason={current.reason ?? `The ${label} series is not available.`} evidenceNeeded={`Real ${label} observations inside the project boundary for at least two periods.`} />
      ) : (
        <>
          <p className={styles.muted}>
            {current.source ? `Source: ${current.source}. ` : ''}
            {coverage.length > 0 ? `AOI coverage ${Math.min(...coverage)}% to ${Math.max(...coverage)}% of the project area.` : 'AOI coverage was not computed.'}
          </p>
          {view === 'chart' ? <SeriesChart points={points} gaps={gaps} label={`${label} annual series, index value by year`} /> : points.length > 0 ? <SeriesTable points={points} /> : <p className={styles.notice}>No observed points.</p>}
          {gaps.length > 0 && (
            <p className={styles.notice} aria-label="Observation gaps">
              No observation for {gaps.join(', ')}. Gaps are shown as gaps and are never interpolated.
            </p>
          )}
          <div className={styles.legend}>
            <span>Circle: derived</span>
            <span>Diamond: model estimated</span>
            <span>Dashed ring: no observation</span>
          </div>
        </>
      )}
    </Card>
  );
}
