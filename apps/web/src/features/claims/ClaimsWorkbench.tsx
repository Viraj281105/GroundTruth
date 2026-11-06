'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, EmptyState, Skeleton } from '../../components/ds';
import { BarList } from '../../components/charts';
import { claimPairs } from './pairs';
import { getCases } from '../../lib/api';
import type { CaseSummary } from '../../lib/types';
import { CLAIMS_COPY as C } from './copy';
import { analyzeClaims, MAX_TEXT_CHARS, type AnalyzeResult, type ClaimsResponse } from './client';
import { segmentText } from './highlight';
import styles from './ClaimsWorkbench.module.css';

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 });

type State = { phase: 'idle' } | { phase: 'loading' } | { phase: 'done'; text: string; data: ClaimsResponse } | { phase: 'failed'; result: Exclude<AnalyzeResult, { kind: 'ok' }> };

export function ClaimsWorkbench() {
  const [text, setText] = useState('');
  const [caseId, setCaseId] = useState('');
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [state, setState] = useState<State>({ phase: 'idle' });
  const [active, setActive] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    getCases().then((r) => setCases(r.data), () => setCases([]));
  }, []);

  async function run() {
    if (!text.trim()) return;
    if (text.length > MAX_TEXT_CHARS) {
      setLocalError(C.tooLong);
      return;
    }
    setLocalError(null);
    setActive(null);
    setState({ phase: 'loading' });
    const submitted = text;
    const result = await analyzeClaims(submitted, caseId || null);
    setState(result.kind === 'ok' ? { phase: 'done', text: submitted, data: result.data } : { phase: 'failed', result });
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!(file.type.startsWith('text/') || /\.(txt|md)$/i.test(file.name))) {
      setLocalError(C.notFileType);
      return;
    }
    setLocalError(null);
    setText(await file.text());
  }

  const segments = useMemo(
    () => (state.phase === 'done' ? segmentText(state.text, state.data.claims.map((c) => c.span)) : []),
    [state],
  );

  return (
    <div className={`gt-container ${styles.wrap}`}>
      <header>
        <h1 className={styles.title}>{C.title}</h1>
        <p className={styles.intro}>{C.intro}</p>
      </header>
      <div className={styles.banner} role="note">{C.banner}</div>
      <div className={styles.layout}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="claims-text">{C.textLabel}</label>
          <textarea
            id="claims-text"
            className={`${styles.textarea} ${dragging ? styles.dragging : ''}`}
            value={text}
            placeholder={C.placeholder}
            onChange={(e) => setText(e.target.value)}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          />
          <p className={styles.hint}>{C.dropHint} {text.length.toLocaleString('en-US')} / {MAX_TEXT_CHARS.toLocaleString('en-US')}</p>
          {localError && <p role="alert" className={styles.note}>{localError}</p>}
          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="claims-case">{C.caseLabel}</label>
              <select id="claims-case" className={styles.select} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                <option value="">{C.noCase}</option>
                {cases.map((c) => <option key={c.case_id} value={c.case_id}>{c.name}</option>)}
              </select>
            </div>
            <Button onClick={run} loading={state.phase === 'loading'} disabled={!text.trim()}>{C.analyze}</Button>
            <Button variant="ghost" onClick={() => { setText(''); setState({ phase: 'idle' }); setLocalError(null); }}>{C.clear}</Button>
          </div>
          {state.phase === 'done' && (
            <Card tone="sunken">
              <p className={styles.preview} aria-label="Text with claims highlighted">
                {segments.map((s, i) =>
                  s.claim === null ? <span key={i}>{s.text}</span> : (
                    <mark key={i} id={`claim-${s.claim}`} className={`${styles.mark} ${active === s.claim ? styles.markActive : ''}`}>{s.text}</mark>
                  ),
                )}
              </p>
            </Card>
          )}
        </div>
        <aside aria-label={C.panelTitle} aria-live="polite">
          <Panel state={state} active={active} setActive={setActive} />
        </aside>
      </div>
    </div>
  );
}

function Panel({ state, active, setActive }: { state: State; active: number | null; setActive: (i: number | null) => void }) {
  if (state.phase === 'idle') return <EmptyState title={C.emptyTitle} body={C.emptyBody} />;
  if (state.phase === 'loading') {
    return (
      <div className={styles.skel} aria-busy="true">
        <Skeleton height="4rem" /><Skeleton height="4rem" /><Skeleton height="4rem" />
      </div>
    );
  }
  if (state.phase === 'failed') {
    const unreachable = state.result.kind === 'unreachable';
    return (
      <div className={styles.error} role="alert">
        <strong>{unreachable ? C.errorTitle : C.rejectedTitle}</strong>
        <p className={styles.note}>{state.result.kind === 'rejected' ? state.result.message : C.errorBody}</p>
      </div>
    );
  }
  const { data } = state;
  if (data.claims.length === 0) return <EmptyState title={C.noneFoundTitle} body={C.noneFoundBody} />;
  return (
    <div className={styles.field}>
      <h2 style={{ fontSize: 'var(--text-xl)', margin: 0 }}>{C.panelTitle} ({data.claims.length})</h2>
      <ul className={styles.list}>
        {data.claims.map((c, i) => {
          const cmp = data.comparisons[i];
          return (
            <li key={`${c.span.start}-${i}`}>
              <button
                type="button"
                className={`${styles.item} ${active === i ? styles.itemActive : ''}`}
                onClick={() => { setActive(i); document.getElementById(`claim-${i}`)?.scrollIntoView({ block: 'center' }); }}
              >
                <span className={styles.kind}>{C.kinds[c.kind] ?? c.kind}</span>
                <span className={styles.pair}>
                  <span><span className={styles.pairLabel}>{C.claimed}</span><span className="num">{fmt(c.value)} {c.unit}</span></span>
                  <span><span className={styles.pairLabel}>{C.estimate}</span><span className="num">{cmp && cmp.estimated !== null ? `${fmt(cmp.estimated)} ${c.unit}` : C.notAvailable}</span></span>
                </span>
                {cmp && <span className={styles.note}>{cmp.note}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <PairChart data={data} />
      <p className={styles.hint}>{data.disclaimer}</p>
    </div>
  );
}

function PairChart({ data }: { data: ClaimsResponse }) {
  const pairs = claimPairs(data);
  if (pairs.length === 0) return <p className={styles.note}>{C.pairsNone}</p>;
  return (
    <Card tone="sunken">
      <h3 style={{ fontSize: 'var(--text-base)', margin: '0 0 var(--space-3)' }}>{C.pairsTitle}</h3>
      <div className={styles.field}>
        {pairs.map((p) => (
          <div key={p.index}>
            <p className={styles.pairLabel}>{C.kinds[p.kind] ?? p.kind} ({p.unit})</p>
            <BarList
              label={`${C.kinds[p.kind] ?? p.kind}: stated ${fmt(p.claimed)} ${p.unit}, comparison ${fmt(p.estimated)} ${p.unit}`}
              items={[
                { label: C.pairClaimed, value: p.claimed, tone: 'caution', display: fmt(p.claimed) },
                { label: C.pairEstimated, value: p.estimated, tone: 'synthetic', display: fmt(p.estimated) },
              ]}
            />
          </div>
        ))}
      </div>
      <p className={styles.hint}>{C.pairsScale}</p>
    </Card>
  );
}
