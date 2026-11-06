'use client';

import React, { useEffect, useState } from 'react';
import { Card, Chip, Skeleton } from '../../components/ds';
import { getHealth } from '../../lib/api';
import type { HealthResponse } from '../../lib/types';
import { STATUS_COPY as C } from './copy';
import { capabilityRows, isUnreachable } from './status';
import styles from './StatusView.module.css';

export function StatusView() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  return (
    <div className={`gt-container ${styles.wrap}`}>
      <header>
        <h1 className={styles.title}>{C.title}</h1>
        <p className={styles.intro}>{C.intro}</p>
      </header>
      {!health && <Skeleton height="12rem" />}
      {health && isUnreachable(health) && (
        <div className={styles.error} role="alert">
          <strong>{C.unreachableTitle}</strong>
          <p>{C.unreachableBody}</p>
        </div>
      )}
      {health && !isUnreachable(health) && (
        <div className={styles.grid}>
          <Card>
            <h2 className={styles.h2}>{C.versions}</h2>
            <ul className={styles.list}>
              {[[C.package, health.version], [C.engine, health.engine_version], [C.contract, health.contract_version]].map(([k, v]) => (
                <li key={k} className={styles.row}><span>{k}</span><span className={styles.mono}>{v}</span></li>
              ))}
              <li className={styles.row}><span>{C.cases}</span><span className="num">{health.cases_available}</span></li>
            </ul>
          </Card>
          <Card>
            <h2 className={styles.h2}>{C.capabilities}</h2>
            <ul className={styles.list}>
              {capabilityRows(health).map((r) => (
                <li key={r.key} className={styles.row}>
                  <span>{r.label}</span>
                  <Chip tone={r.implemented ? 'accent' : 'neutral'}>{r.implemented ? C.implemented : C.notImplemented}</Chip>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
      <div className={styles.sim} role="note">
        <strong>{C.simulatedTitle}</strong>
        <p>{C.simulatedBody}</p>
      </div>
      <Card>
        <h2 className={styles.h2}>{C.guardrailsTitle}</h2>
        <ul className={styles.guard}>{C.guardrails.map((g) => <li key={g}>{g}</li>)}</ul>
      </Card>
    </div>
  );
}
