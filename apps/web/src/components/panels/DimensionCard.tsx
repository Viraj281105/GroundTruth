import React from 'react';
import { Card, StatusChip } from '../ds';
import { dimensionView, limitationLabel } from './dimension.model';
import type { DimensionView } from './types';
import styles from './panels.module.css';

function Items({ label, items }: { label: string; items: readonly string[] | null | undefined }) {
  if (!items || items.length === 0) return null;
  return (
    <div className={styles.lists}>
      <span className={styles.listLabel}>{label}</span>
      <ul>
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/** Renders a dimension's status by its `status_kind`; "Insufficient evidence" is never styled as success. */
export function DimensionStatus({ dimension }: { dimension: Pick<DimensionView, 'status' | 'status_kind'> }) {
  const v = dimensionView(dimension);
  if (v.kind === 'trend' && v.chipStatus) return <StatusChip status={v.chipStatus} />;
  return (
    <span className={`${styles.kindChip} ${styles[`tone_${v.tone}`]}`} role="img" aria-label={`${v.kind === 'quality' ? 'Evidence quality' : 'Status'}: ${v.label}`}>
      <span aria-hidden="true">{v.icon}</span>
      <span aria-hidden="true">{v.label}</span>
    </span>
  );
}

export function DimensionCard({ dimension: d }: { dimension: DimensionView }) {
  const v = dimensionView(d);
  return (
    <Card className={styles.dim} data-dimension-id={d.id} data-dim-kind={v.kind} data-dim-tone={v.tone} data-dim-label={v.label}>
      <div className={styles.dimHead}>
        <h3>{d.title}</h3>
        <DimensionStatus dimension={d} />
      </div>
      <p className={styles.find}>{d.finding}</p>
      <Items label="Known" items={d.known} />
      <Items label="Suggested" items={d.suggested} />
      <Items label="Cannot establish" items={d.cannot_establish} />
      <div className={styles.foot}>
        <div className={styles.row}>
          <span className={styles.listLabel}>Limitation</span>
          <span className={`${styles.kindChip} ${styles.tone_neutral}`} data-limitation={d.limitation}>
            {limitationLabel(d.limitation)}
          </span>
          <span className={styles.confidence}>Confidence: {d.confidence}</span>
        </div>
        {d.evidence_needed && (
          <div>
            <span className={styles.listLabel}>Evidence needed</span> {d.evidence_needed}
          </div>
        )}
      </div>
    </Card>
  );
}
