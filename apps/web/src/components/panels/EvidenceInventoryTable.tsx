import React from 'react';
import { Card, UnavailablePanel } from '../ds';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { inventoryRows } from './inventory.model';
import { isUnavailable, type AccessLevel, type EvidenceInventoryView, type PanelProps } from './types';
import styles from './panels.module.css';

export interface EvidenceInventoryTableProps extends PanelProps<EvidenceInventoryView> {
  level: AccessLevel | string;
}

/** Summary at `view`; scene-level rows with checksums and scene ids only when the payload has them. */
export function EvidenceInventoryTable({ data, loading, level }: EvidenceInventoryTableProps) {
  if (loading) return <PanelLoading label="evidence inventory" />;
  if (!data) return <PanelEmpty title="No evidence inventory" body="The inventory lists the evidence stored for this project." />;
  if (isUnavailable(data)) {
    return <UnavailablePanel title="Evidence inventory" reason={data.reason ?? 'No evidence has been stored for this project.'} evidenceNeeded="An ingest run that stores real observations for the project." />;
  }
  const m = inventoryRows(data, level);
  return (
    <Card className={styles.panel} aria-label="Evidence inventory">
      <h3 className={styles.title}>Evidence inventory</h3>
      {m.summary.length === 0 ? (
        <p className={styles.notice}>No indicators are stored.</p>
      ) : (
        <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Evidence inventory by indicator, scrollable">
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Indicator</th>
                <th>Status</th>
                <th>Records</th>
                <th>Years</th>
                <th>Sensors</th>
                <th>Origin</th>
              </tr>
            </thead>
            <tbody>
              {m.summary.map((r) => (
                <tr key={r.indicator}>
                  <td>{r.indicator}</td>
                  <td>{r.status === 'available' ? 'Available' : `Unavailable${r.reason ? `: ${r.reason}` : ''}`}</td>
                  <td className={styles.numcell}>{r.nRecords}</td>
                  <td>{r.years.join(', ') || '-'}</td>
                  <td>{r.sensors.join(', ') || '-'}</td>
                  <td>{r.dataOrigin ?? r.source ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className={styles.muted}>Climate record: {data.climate_status === 'available' ? 'available' : `unavailable${data.climate_reason ? ` (${data.climate_reason})` : ''}`}</p>
      {m.boundarySha256 && (
        <p className={styles.muted}>
          Boundary checksum <span className={styles.mono}>{m.boundarySha256}</span>
        </p>
      )}
      {m.items.length > 0 && (
        <details className={styles.collapsibleBlock}>
          <summary className={styles.collapsibleSummary}>
            <span>Cryptographic checksums & scene IDs ({m.items.length} records)</span>
          </summary>
          <div className={styles.collapsibleContent}>
            <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Scene and checksum records, scrollable">
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Indicator</th>
                    <th>Year</th>
                    <th>Scenes</th>
                    {m.showSceneIds && <th>Scene ids</th>}
                    {m.showChecksum && <th>Checksum</th>}
                  </tr>
                </thead>
                <tbody>
                  {m.items.map((i) => (
                    <tr key={`${i.indicator}-${i.year}`}>
                      <td>{i.indicator}</td>
                      <td>{i.year}</td>
                      <td className={styles.numcell}>{i.nScenes}</td>
                      {m.showSceneIds && <td className={styles.mono}>{i.sceneIds ? i.sceneIds.join(', ') : ''}</td>}
                      {m.showChecksum && <td className={styles.mono}>{i.scenesSha256 ?? ''}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>
      )}
    </Card>
  );
}
