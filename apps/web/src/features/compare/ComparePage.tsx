'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Button, Card, EmptyState, Skeleton, Stat } from '../../components/ds';
import { getCaseDetail, getCases, getVisualizationFixture } from '../../lib/api';
import type { CaseDetail, CaseSummary } from '../../lib/types';
import { buildCaseViz } from '../cases/viz';
import { CompareCharts } from './CompareCharts';
import { buildCompareUrl, compareRows, parseCompareParams, swapIds } from './compare';
import { COMPARE_COPY as C } from './copy';
import styles from './ComparePage.module.css';

type Load = { phase: 'idle' } | { phase: 'loading' } | { phase: 'ok'; detail: CaseDetail | null } | { phase: 'error' };

function useCase(id: string): Load {
  const [state, setState] = useState<Load>({ phase: 'idle' });
  useEffect(() => {
    if (!id) {
      setState({ phase: 'idle' });
      return;
    }
    let live = true;
    setState({ phase: 'loading' });
    getCaseDetail(id).then(
      (r) => live && setState({ phase: 'ok', detail: r.data }),
      () => live && setState({ phase: 'error' }),
    );
    return () => {
      live = false;
    };
  }, [id]);
  return state;
}

function Column({ id, load }: { id: string; load: Load }) {
  if (load.phase === 'idle') return <EmptyState title={C.emptyTitle} body={C.emptyBody} />;
  if (load.phase === 'loading') return <Skeleton height="14rem" />;
  if (load.phase === 'error') return <div className={styles.error} role="alert">{C.loadError}</div>;
  if (!load.detail) return <div className={styles.error} role="alert">{C.unknownCase}</div>;
  return (
    <div className={styles.col}>
      <h2 className={styles.colTitle}>{load.detail.name}</h2>
      <p className={styles.meta}>{load.detail.country} · {load.detail.standard} · {id}</p>
      {compareRows(load.detail).map((row) => (
        <Card key={row.key} tone="sunken">
          <Stat
            label={row.label}
            value={row.value ?? <span className={styles.missing}>{C.notAvailable}</span>}
            hint={row.value === null ? C.notAvailableHint : undefined}
          />
        </Card>
      ))}
    </div>
  );
}

export function ComparePage() {
  const router = useRouter();
  const pathname = usePathname();
  const ids = parseCompareParams(useSearchParams());
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [copied, setCopied] = useState(false);
  const a = useCase(ids.a);
  const b = useCase(ids.b);

  useEffect(() => {
    getCases().then((r) => setCases(r.data), () => setCases([]));
  }, []);

  const vizA = a.phase === 'ok' && a.detail ? buildCaseViz(getVisualizationFixture(ids.a)) : null;
  const vizB = b.phase === 'ok' && b.detail ? buildCaseViz(getVisualizationFixture(ids.b)) : null;
  const bothLoaded = a.phase === 'ok' && a.detail && b.phase === 'ok' && b.detail;
  const charts =
    a.phase === 'ok' && a.detail && b.phase === 'ok' && b.detail && vizA && vizB ? (
      <CompareCharts a={{ name: a.detail.name, viz: vizA }} b={{ name: b.detail.name, viz: vizB }} />
    ) : bothLoaded ? (
      <p className={styles.missing}>{C.chartsMissing}</p>
    ) : null;

  const go = (next: { a: string; b: string }) => router.replace(buildCompareUrl(next));

  async function share() {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${pathname}${buildCompareUrl(ids).replace('/compare', '')}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const select = (label: string, value: string, set: (v: string) => void) => (
    <div className={styles.field}>
      <label className={styles.label}>
        {label}
        <select className={styles.select} value={value} onChange={(e) => set(e.target.value)}>
          <option value="">{C.choose}</option>
          {value && !cases.some((c) => c.case_id === value) && <option value={value}>{value}</option>}
          {cases.map((c) => <option key={c.case_id} value={c.case_id}>{c.name}</option>)}
        </select>
      </label>
    </div>
  );

  return (
    <div className={`gt-container ${styles.wrap}`}>
      <header>
        <h1 className={styles.title}>{C.title}</h1>
        <p className={styles.intro}>{C.intro}</p>
      </header>
      <div className={styles.controls}>
        {select(C.caseA, ids.a, (v) => go({ ...ids, a: v }))}
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => go(swapIds(ids))}>{C.swap}</Button>
          <Button variant="ghost" onClick={share} aria-live="polite">{copied ? C.copied : C.share}</Button>
        </div>
        {select(C.caseB, ids.b, (v) => go({ ...ids, b: v }))}
      </div>
      <div className={styles.cols}>
        <Column id={ids.a} load={a} />
        <Column id={ids.b} load={b} />
      </div>
      {charts}
    </div>
  );
}
