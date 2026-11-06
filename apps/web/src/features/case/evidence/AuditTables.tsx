'use client';

import React from 'react';
import type { VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import type { Evidence } from '../../../lib/types';
import { sig } from '../../../lib/evidence';
import { Card } from './VizBits';
import styles from './viz.module.css';

/** Auditor-only tables: the per-period residual series, per-candidate donors and the evidence ids. */
export function AuditTables({ items, viz, onSelect }: { items: Evidence[]; viz: VerificationFixtureData | null; onSelect: (e: Evidence) => void }) {
  return (
    <div className={styles.grid}>
      <Card title="Residual series (observed minus counterfactual)">
        {viz && viz.chartSeries.length > 0 ? (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Observed</th>
                  <th>Counterfactual</th>
                  <th>Gap</th>
                </tr>
              </thead>
              <tbody>
                {viz.chartSeries.map((p) => (
                  <tr key={p.year}>
                    <td>{p.year}</td>
                    <td>{sig(p.observed, 4)}</td>
                    <td>{sig(p.synthetic, 4)}</td>
                    <td>{sig(p.gap, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={styles.cardNote}>Not available: no per-period series was provided.</p>
        )}
      </Card>
      <Card title="Donor candidates">
        {viz && viz.donorPool.length > 0 ? (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Unit</th>
                  <th>Admitted</th>
                  <th>Distance</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {viz.donorPool.map((d) => (
                  <tr key={d.unit_id}>
                    <td>{d.unit_id}</td>
                    <td>{d.admitted ? 'yes' : 'no'}</td>
                    <td>{sig(d.distance, 3)}</td>
                    <td>{d.exclusion_reason ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className={styles.cardNote}>Not available: no per-candidate outcomes were provided.</p>
        )}
      </Card>
      <Card title="Evidence ids">
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <button type="button" onClick={() => onSelect(e)} style={{ all: 'unset', cursor: 'pointer', textDecoration: 'underline', color: 'var(--accent)' }}>
                      {e.id}
                    </button>
                  </td>
                  <td>{typeof e.value === 'number' ? sig(e.value, 4) : String(e.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
