import React from 'react';
import { Card, UnavailablePanel } from '../ds';
import { extent, linearScale, niceTicks, compact } from '../charts';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { climateAnnual, type ClimateRow } from './climate.model';
import { isUnavailable, type ClimateView, type PanelProps } from './types';
import styles from './panels.module.css';

const W = 520;
const H = 200;
const PAD = { l: 44, r: 12, t: 12, b: 28 };

function RainfallBars({ rows }: { rows: ClimateRow[] }) {
  const d = extent(rows.map((r) => r.rainfallMm ?? Number.NaN));
  if (!d || rows.length === 0) return null;
  const y = linearScale({ min: 0, max: d.max }, [H - PAD.b, PAD.t]);
  const slot = (W - PAD.l - PAD.r) / rows.length;
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Annual rainfall in mm by year, coloured by SPI-12 flag" data-chart="rainfall">
      {niceTicks({ min: 0, max: d.max }, 5).map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className={styles.grid} />
          <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" className={styles.tick}>
            {compact(t)}
          </text>
        </g>
      ))}
      <text x={4} y={10} className={styles.tick}>mm</text>
      {rows.map((r, i) => {
        const cx = PAD.l + slot * i + slot / 2;
        const bw = Math.min(slot * 0.6, 40);
        const cls = r.flag === 'drought' ? styles.barDry : r.flag === 'wet' ? styles.barWet : styles.barNeutral;
        return (
          <g key={r.year}>
            {r.rainfallMm !== null && (
              <rect x={cx - bw / 2} y={y(r.rainfallMm)} width={bw} height={H - PAD.b - y(r.rainfallMm)} className={`${cls} ${r.context ? styles.barContext : ''}`}>
                <title>{`${r.year}: ${r.rainfallMm} mm${r.spi12 !== null ? `, SPI-12 ${r.spi12}` : ''}${r.context ? ' (context only)' : ''}`}</title>
              </rect>
            )}
            {i % Math.ceil(rows.length / 10) === 0 && (
              <text x={cx} y={H - 8} textAnchor="middle" className={styles.tick}>
                {r.year}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export interface ClimatePanelProps extends PanelProps<ClimateView> {
  /** Years the vegetation series covers; other years are labelled as context only. */
  observedWindow?: { from: number; to: number } | null;
}

export function ClimatePanel({ data, loading, observedWindow }: ClimatePanelProps) {
  if (loading) return <PanelLoading label="climate" />;
  if (!data) return <PanelEmpty title="No climate record" body="Climate context appears once a climate bundle is attached." />;
  if (isUnavailable(data)) {
    return <UnavailablePanel title="Climate context" reason={data.reason ?? 'The climate record is not available.'} evidenceNeeded="A climate bundle (rainfall and SPI-12) overlapping the observed years." />;
  }
  const { rows, missingMonths } = climateAnnual(data, observedWindow);
  return (
    <Card className={styles.panel} aria-label="Climate context">
      <h3 className={styles.title}>Rainfall and drought</h3>
      {rows.length === 0 ? <p className={styles.notice}>No annual climate rows were returned.</p> : <RainfallBars rows={rows} />}
      <div className={styles.legend}>
        <span>Red bar: served drought classification</span>
        <span>Blue bar: served wet classification</span>
        <span>Faded: outside the observed window (context only)</span>
      </div>
      {rows.length > 0 && (
        <details className={styles.collapsibleBlock}>
          <summary className={styles.collapsibleSummary}>
            <span>Annual climate breakdown table ({rows.length} years)</span>
          </summary>
          <div className={styles.collapsibleContent}>
            <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Annual climate table, scrollable">
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>Rainfall (mm)</th>
                    <th>SPI-12</th>
                    <th>Flag</th>
                    <th>Months</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.year} className={r.context ? styles.contextRow : undefined} data-flag={r.flag}>
                      <td>
                        {r.year}
                        {r.context ? ' (context only)' : ''}
                      </td>
                      <td className={styles.numcell}>{r.rainfallMm ?? 'no data'}</td>
                      <td className={styles.numcell}>{r.spi12 ?? 'no data'}</td>
                      <td>{r.flag === 'drought' ? `Drought (${r.droughtClass.replace(/_/g, ' ')})` : r.flag === 'wet' ? `Wet (${r.droughtClass.replace(/_/g, ' ')})` : r.droughtClass ? r.droughtClass.replace(/_/g, ' ') : 'Not classified'}</td>
                      <td className={styles.numcell}>
                        {r.validMonths}/12{r.complete ? '' : ' (incomplete)'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      )}
      <div aria-label="Missing months">
        <span className={styles.listLabel}>Missing months</span>
        {missingMonths.length === 0 ? <p className={styles.muted}>No months are missing from the record.</p> : <p className={styles.mono}>{missingMonths.join(', ')}</p>}
      </div>
      {data.sources.length > 0 && <p className={styles.muted}>Sources: {data.sources.map((s) => s.name).join('; ')}</p>}
    </Card>
  );
}
