import React from 'react';
import { Chip } from '../ds';
import { DimensionStatus } from './DimensionCard';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { portfolioRows, type PortfolioRowModel } from './portfolio.model';
import type { DimensionStatusView } from './dimension.model';
import type { PanelProps, PortfolioView } from './types';
import styles from './panels.module.css';

const asDim = (v: DimensionStatusView) => ({ status: v.label, status_kind: v.kind === 'trend' ? ('trend_status' as const) : v.kind === 'quality' ? ('quality_rating' as const) : ('attribution_verdict' as const) });

function Table({ rows, heading }: { rows: PortfolioRowModel[]; heading: string }) {
  return (
    <div className={styles.tableWrap} role="region" tabIndex={0} aria-label={`${heading}, scrollable`}>
      <table className={styles.table} aria-label={heading}>
        <thead>
          <tr>
            <th>Project</th>
            <th>Access</th>
            <th>Assessment level</th>
            <th>Trajectory</th>
            <th>Risk</th>
            <th>Evidence quality</th>
            <th>Top recommendation</th>
            <th>Attribution</th>
            <th>Evidence confidence</th>
            <th>Reported funding</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.degraded ? styles.degradedRow : undefined} data-degraded={r.degraded}>
              <td>
                <strong>{r.name}</strong>
                {r.simulated && (
                  <>
                    {' '}
                    <Chip tone="sim">Simulated data</Chip>
                  </>
                )}
              </td>
              <td>
                <Chip>{r.accessLevel}</Chip>
              </td>
              <td>{r.degraded ? '-' : `Level ${r.level} · ${r.levelName}`}</td>
              {r.degraded || !r.headline ? (
                <td colSpan={6}>
                  {r.degraded ? <Chip tone="caution">{r.degradedLabel ?? 'Assessment unavailable'}</Chip> : <span className={styles.muted}>Not reported at this access level</span>}
                </td>
              ) : (
                <>
                  <td>
                    <DimensionStatus dimension={asDim(r.headline.trajectory)} />
                  </td>
                  <td>
                    <DimensionStatus dimension={asDim(r.headline.risk)} />
                  </td>
                  <td>
                    <DimensionStatus dimension={asDim(r.headline.evidenceQuality)} />
                  </td>
                  <td>{r.topRecommendation ?? <span className={styles.muted}>None triggered</span>}</td>
                  <td>{r.verdict ?? '-'}</td>
                  <td>{r.confidence ?? '-'}</td>
                </>
              )}
              <td>
                {r.funding ? (
                  <>
                    <span className={styles.numcell}>{r.funding.text}</span>
                    <br />
                    <span className={styles.muted}>reported by {r.funding.reportedBy}</span>
                  </>
                ) : (
                  <span className={styles.muted}>Not reported</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Real projects and SIMULATED projects in separate sections. No totals, no aggregate score. */
export function PortfolioTable({ data, loading }: PanelProps<PortfolioView>) {
  if (loading) return <PanelLoading label="portfolio" />;
  if (!data) return <PanelEmpty title="No portfolio" body="Projects shared with this organization appear here." />;
  const { real, simulated } = portfolioRows(data);
  if (real.length === 0 && simulated.length === 0) return <PanelEmpty title="No projects" body="No project has been shared with this organization yet." />;
  return (
    <section className={styles.panel} aria-label="Portfolio">
      <div data-section="real" className={styles.panel}>
        <h3 className={styles.title}>Projects</h3>
        {real.length > 0 ? <Table rows={real} heading="Projects" /> : <p className={styles.notice}>No real projects are shared with this organization.</p>}
      </div>
      {simulated.length > 0 && (
        <div data-section="simulated" className={styles.simSection}>
          <h3 className={styles.title}>Simulated projects</h3>
          <p className={styles.lead}>SIMULATED DATA. These are never combined with the projects above.</p>
          <Table rows={simulated} heading="Simulated projects" />
        </div>
      )}
    </section>
  );
}
