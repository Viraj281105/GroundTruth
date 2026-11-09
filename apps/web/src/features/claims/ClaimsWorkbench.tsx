'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Chip, EmptyState, Skeleton } from '../../components/ds';
import { BarList } from '../../components/charts';
import { claimPairs } from './pairs';
import { getApiBaseUrl, getCases } from '../../lib/api';
import type { CaseSummary } from '../../lib/types';
import { CLAIMS_COPY as C } from './copy';
import { analyzeClaims, MAX_TEXT_CHARS, type AnalyzeResult, type ClaimsResponse } from './client';
import { segmentText } from './highlight';
import { formatStatementValue, highlightSpans, statementIndexForClaim, statementLabel, statementsOf, statementTone, unrecognisedOf } from './statements';
import styles from './ClaimsWorkbench.module.css';

const REAL_DOCUMENTS = [
  {
    label: 'Kariba REDD+ (VCS 902)',
    caseId: 'kariba-redd',
    text: `Project Name: Kariba REDD+ Project
Registry: Verra VCS 902
Proponent: Carbon Green Investments (Guernsey)
Country: Zimbabwe
Ecosystem: Miombo woodland / dry forest
Project Area: 784,987 hectares inside the four Rural District Councils (Binga, Nyaminyami, Hurungwe, and Mbire).
Crediting Period: 2011-07-01 to 2041-06-30 (30-year crediting period).
Credits Claimed: Over the initial monitoring cycles, the project claimed and issued 26,822,953 credits (tCO2e) of verified emissions reductions.
Baseline emissions avoided: 1,450,000 tCO2e per year across the project accounting area.`,
  },
  {
    label: 'Kasigau Corridor (VCS 562)',
    caseId: 'kasigau-corridor-redd',
    text: `Project Name: The Kasigau Corridor REDD Project Phase II - The Community Ranches
Registry: Verra VCS 562
Proponent: Wildlife Works Carbon LLC
Country: Kenya
Ecosystem: Dryland acacia-commiphora forest
Project Area: 169,741 hectares connecting Tsavo East and Tsavo West National Parks.
Crediting Period: 2011-01-01 to 2040-12-31.
Credits Claimed: Total claimed credits issued: 13,800,000 tCO2e.
Estimated annual avoided deforestation reduction: 1,350,000 tCO2e per year.`,
  },
  {
    label: 'Rimba Raya (VCS 641)',
    caseId: 'rimba-raya-redd',
    text: `Project Name: Rimba Raya Biodiversity Reserve Project
Registry: Verra VCS 641
Proponent: InfiniteEARTH Limited
Country: Indonesia
Ecosystem: Tropical peat swamp forest
Project Area: 64,977 hectares adjacent to Tanjung Puting National Park in Central Kalimantan.
Crediting Period: 2009-01-01 to 2038-12-31.
Credits Claimed: Total claimed and verified carbon credits issued: 33,200,000 tCO2e.
Average annual emission reductions avoided: 3,520,000 tCO2e.`,
  },
];

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

    if (file.name.toLowerCase().endsWith('.pdf')) {
      setLocalError(null);
      setState({ phase: 'loading' });
      const reader = new FileReader();
      reader.onload = async () => {
        const resultStr = reader.result as string;
        const base64 = resultStr.includes(',') ? resultStr.split(',')[1] : resultStr;
        try {
          const res = await fetch(`${getApiBaseUrl()}/claims/extract-pdf`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ file_base64: base64, filename: file.name }),
          });
          if (res.ok) {
            const data = await res.json();
            setText(data.text);
            setState({ phase: 'idle' });
          } else {
            setLocalError('Failed to extract text from PDF.');
            setState({ phase: 'idle' });
          }
        } catch {
          setLocalError('API unreachable for PDF text extraction.');
          setState({ phase: 'idle' });
        }
      };
      reader.readAsDataURL(file);
      return;
    }

    if (!(file.type.startsWith('text/') || /\.(txt|md)$/i.test(file.name))) {
      setLocalError(C.notFileType);
      return;
    }
    setLocalError(null);
    setText(await file.text());
  }

  const segments = useMemo(
    () => (state.phase === 'done' ? segmentText(state.text, highlightSpans(state.data)) : []),
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
          <div className={styles.sampleBar}>
            <span className={styles.sampleLabel}>Load real document:</span>
            {REAL_DOCUMENTS.map((doc) => (
              <button
                key={doc.caseId}
                type="button"
                className={styles.sampleBtn}
                onClick={() => {
                  setText(doc.text);
                  setCaseId(doc.caseId);
                  setLocalError(null);
                  setState({ phase: 'idle' });
                }}
              >
                {doc.label}
              </button>
            ))}
          </div>
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
                    <mark key={i} id={`stmt-${s.claim}`} className={`${styles.mark} ${active === s.claim ? styles.markActive : ''}`}>{s.text}</mark>
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
  const statements = statementsOf(data);
  const unrecognised = unrecognisedOf(data);
  if (data.claims.length === 0 && statements.length === 0 && unrecognised.length === 0) return <EmptyState title={C.noneFoundTitle} body={C.noneFoundBody} />;
  return (
    <div className={styles.field}>
      <h2 style={{ fontSize: 'var(--text-xl)', margin: 0 }}>{C.panelTitle} ({data.claims.length})</h2>
      {data.claims.length === 0 && <p className={styles.note}>{C.noneFoundBody}</p>}
      <ul className={styles.list}>
        {data.claims.map((c, i) => {
          const cmp = data.comparisons[i];
          return (
            <li key={`${c.span.start}-${i}`}>
              <button
                type="button"
                className={`${styles.item} ${active !== null && active === statementIndexForClaim(data, i) ? styles.itemActive : ''}`}
                onClick={() => { const k = statementIndexForClaim(data, i); setActive(k); document.getElementById(`stmt-${k}`)?.scrollIntoView?.({ block: 'center' }); }}
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
      <StatementList data={data} active={active} setActive={setActive} />
      <PairChart data={data} />
      <UnclassifiedList data={data} />
      <p className={styles.hint}>{data.disclaimer || C.fallbackDisclaimer}</p>
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

/** Every statement read from the text, with its status and why. Extraction is never presented as verification. */
export function StatementList({ data, active, setActive }: { data: ClaimsResponse; active?: number | null; setActive?: (i: number | null) => void }) {
  const statements = statementsOf(data);
  if (statements.length === 0) return null;
  return (
    <section className={styles.field} aria-label={C.statementsTitle}>
      <h3 style={{ fontSize: 'var(--text-base)', margin: 0 }}>{C.statementsTitle} ({statements.length})</h3>
      <p className={styles.hint}>{C.statementsHint}</p>
      <ul className={styles.list}>
        {statements.map((st, i) => {
          const value = formatStatementValue(st);
          return (
            <li key={st.statement_id || i} data-statement-status={st.status}>
              <button
                type="button"
                className={`${styles.item} ${active === i ? styles.itemActive : ''}`}
                onClick={() => { setActive?.(i); document.getElementById(`stmt-${i}`)?.scrollIntoView?.({ block: 'center' }); }}
              >
                <span className={styles.stmtHead}>
                  <Chip tone={statementTone(st.status)}>{statementLabel(st.status)}</Chip>
                  <span className={styles.pairLabel}>{C.kinds[st.kind] ?? st.kind}</span>
                </span>
                <q className={styles.quote}>{st.text}</q>
                {value && <span className="num">{value}</span>}
                {st.reason && <span className={styles.note}>{st.reason}</span>}
                {st.evidence_gap && <span className={styles.note}><b>{C.evidenceGap}</b> {st.evidence_gap}</span>}
                {st.evidence_link && <span className={styles.note}><b>{C.evidenceLink}</b> {st.evidence_link}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Sentences the extractor could not classify, listed so nothing is silently ignored. */
export function UnclassifiedList({ data }: { data: ClaimsResponse }) {
  const items = unrecognisedOf(data);
  if (items.length === 0) return null;
  return (
    <section className={styles.field} aria-label={C.unclassifiedTitle}>
      <h3 style={{ fontSize: 'var(--text-base)', margin: 0 }}>{C.unclassifiedTitle} ({items.length})</h3>
      <p className={styles.hint}>{C.unclassifiedHint}</p>
      <ul className={styles.list}>
        {items.map((u, i) => (
          <li key={`${u.start}-${i}`} className={styles.item}>
            <q className={styles.quote}>{u.text}</q>
          </li>
        ))}
      </ul>
    </section>
  );
}
