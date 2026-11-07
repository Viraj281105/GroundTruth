'use client';

import React, { useEffect, useState } from 'react';
import { CheckCircle2, CircleDashed } from 'lucide-react';
import { Card, Chip, EmptyState, Skeleton } from '../../components/ds';
import { BarList } from '../../components/charts';
import { getHealth } from '../../lib/api';
import type { HealthResponse } from '../../lib/types';
import { STATUS_COPY as C } from './copy';
import { capabilityRows, isUnreachable } from './status';
import { fetchRuns, resultStateCounts, runsPerDay, type RunsResult } from './runs';
import styles from './StatusView.module.css';

export function StatusView() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const [runs, setRuns] = useState<RunsResult | null>(null);

  useEffect(() => {
    getHealth().then(setHealth);
    fetchRuns().then(setRuns);
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
        </div>
      )}
      {health && !isUnreachable(health) && (
        <section aria-labelledby="caps-title">
          <h2 id="caps-title" className={styles.h2}>{C.capabilities}</h2>
          <ul className={styles.caps}>
            {capabilityRows(health).map((r) => (
              <li key={r.key} className={`${styles.cap} ${r.implemented ? styles.capOn : ''}`}>
                {r.implemented ? <CheckCircle2 size={22} aria-hidden="true" /> : <CircleDashed size={22} aria-hidden="true" />}
                <span className={styles.capLabel}>{r.label}</span>
                <Chip tone={r.implemented ? 'accent' : 'neutral'}>{r.implemented ? C.implemented : C.notImplemented}</Chip>
              </li>
            ))}
          </ul>
        </section>
      )}
      <Card>
        <h2 className={styles.h2}>{C.runsTitle}</h2>
        {!runs && <Skeleton height="6rem" />}
        {runs?.kind === 'not_configured' && <EmptyState title={C.runsNotConfiguredTitle} body={C.runsNotConfiguredBody} />}
        {runs?.kind === 'unreachable' && <EmptyState title={C.runsUnreachableTitle} body={C.runsUnreachableBody} />}
        {runs?.kind === 'ok' && runs.items.length === 0 && <EmptyState title={C.runsNoneTitle} body={C.runsNoneBody} />}
        {runs?.kind === 'ok' && runs.items.length > 0 && <RunsPanel runs={runs} />}
      </Card>
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

function RunsPanel({ runs }: { runs: Extract<RunsResult, { kind: 'ok' }> }) {
  const days = runsPerDay(runs.items);
  const top = Math.max(...days.map((d) => d.count));
  const states = resultStateCounts(runs.items);
  return (
    <div className={styles.runs}>
      {runs.containsSimulated && <Chip tone="sim">{C.runsSimulated}</Chip>}
      <div>
        <h3 className={styles.h3}>{C.runsPerDay}</h3>
        <ul className={styles.cols} role="img" aria-label={C.runsPerDayLabel(days.length, runs.items.length)}>
          {days.slice(-14).map((d) => (
            <li key={d.day} className={styles.colItem} title={`${d.day}: ${d.count}`}>
              <span className={`${styles.colNum} num`}>{d.count}</span>
              <span className={styles.colTrack}><span className={styles.colBar} style={{ height: `${Math.max(8, (d.count / top) * 100)}%` }} /></span>
              <span className={styles.colDay}>{d.day.slice(5)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className={styles.h3}>{C.runsByState}</h3>
        <BarList label={C.runsByState} items={states.map((s) => ({ label: s.state, value: s.count, tone: s.state === 'measured' ? 'accent' : s.state === 'failed' ? 'danger' : 'neutral' }))} />
      </div>
      <div>
        <h3 className={styles.h3}>{C.runsRecent}</h3>
        <ul className={styles.list}>
          {runs.items.slice(0, 6).map((r) => (
            <li key={r.run_id} className={styles.row}>
              <span className={styles.mono}>{r.case_id}</span>
              <span className={styles.rowMeta}>
                <Chip tone={r.result_state === 'measured' ? 'accent' : 'neutral'}>{r.result_state}</Chip>
                <time dateTime={r.created_at}>{r.created_at.slice(0, 16).replace('T', ' ')}</time>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
