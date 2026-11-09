import React from 'react';
import { Card } from '../../components/ds';
import type { Schemas } from '../../lib/api-client';
import styles from './projects.module.css';

/**
 * Concise summary of the evidence bundle behind a completed verification (weights, placebo, leave-one-out,
 * spec curve live in its items). Rendered only when the payload carries a bundle, which the API sends at
 * owner and audit levels. The legacy case evidence components are not reused: they need the case view model.
 */
export function DiagnosticsSummary({ bundle }: { bundle: Schemas['EvidenceBundle'] }) {
  return (
    <Card aria-label="Diagnostics">
      <h3 style={{ margin: '0 0 var(--space-2)' }}>Diagnostics</h3>
      <p className={styles.muted}>
        {bundle.items.length} evidence items from the completed run. Values are as computed by the engine; none is a carbon quantity.
      </p>
      {bundle.verdict?.divergence_ratio != null && <p className={styles.muted}>Divergence ratio: {bundle.verdict.divergence_ratio}</p>}
      <details className={styles.collapsibleBlock}>
        <summary className={styles.collapsibleSummary}>
          <span>View {bundle.items.length} evidence diagnostic items</span>
        </summary>
        <div className={styles.collapsibleContent}>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Evidence</th>
                  <th>Value</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {bundle.items.map((it) => (
                  <tr key={it.id}>
                    <td>
                      {it.label}
                      <div className={styles.muted}>{it.id}</div>
                    </td>
                    <td>
                      {String(it.value)} {it.unit}
                    </td>
                    <td>{it.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </details>
      {bundle.warnings.length > 0 && (
        <ul className={styles.muted} style={{ marginTop: 'var(--space-2)' }}>
          {bundle.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
