'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, EmptyState } from '../../components/ds';
import type { CaseSummary } from '../../lib/types';
import { CaseCard } from './CaseCard';
import { casesCopy as c } from './copy';
import { DEFAULT_QUERY, distinct, filterCases, statusInfo, type CaseQuery, type SortKey } from './filter';
import styles from './CasesBrowser.module.css';

function isTyping(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el as HTMLElement).isContentEditable;
}

export function CasesBrowser({ cases, series = {} }: { cases: CaseSummary[]; series?: Record<string, number[]> }) {
  const [query, setQuery] = useState<CaseQuery>(DEFAULT_QUERY);
  const searchRef = useRef<HTMLInputElement>(null);
  const standards = useMemo(() => distinct(cases, 'standard'), [cases]);
  const statuses = useMemo(() => distinct(cases, 'status'), [cases]);
  const shown = useMemo(() => filterCases(cases, query), [cases, query]);
  const set = (patch: Partial<CaseQuery>) => setQuery((q) => ({ ...q, ...patch }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey && !isTyping(document.activeElement)) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div>
      <div className={styles.controls}>
        <label className={styles.search}>
          <span className={styles.label}>{c.searchLabel}</span>
          <input
            ref={searchRef}
            type="search"
            className={styles.input}
            value={query.search}
            placeholder={c.searchPlaceholder}
            onChange={(e) => set({ search: e.target.value })}
          />
        </label>
        <label>
          <span className={styles.label}>{c.standard}</span>
          <select className={styles.input} value={query.standard} onChange={(e) => set({ standard: e.target.value })}>
            <option value="all">{c.all}</option>
            {standards.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>
          <span className={styles.label}>{c.status}</span>
          <select className={styles.input} value={query.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="all">{c.all}</option>
            {statuses.map((s) => <option key={s} value={s}>{statusInfo(s).label}</option>)}
          </select>
        </label>
        <label>
          <span className={styles.label}>{c.sort}</span>
          <select className={styles.input} value={query.sort} onChange={(e) => set({ sort: e.target.value as SortKey })}>
            <option value="name">{c.sortName}</option>
            <option value="standard">{c.sortStandard}</option>
            <option value="period">{c.sortPeriod}</option>
          </select>
        </label>
      </div>
      <p className={styles.count} aria-live="polite">{c.count(shown.length, cases.length)}</p>
      {shown.length === 0 ? (
        <EmptyState
          title={c.noneTitle}
          body={c.noneBody}
          action={<Button variant="secondary" onClick={() => setQuery(DEFAULT_QUERY)}>{c.clear}</Button>}
        />
      ) : (
        <div className={styles.grid}>
          {shown.map((x) => <CaseCard key={x.case_id} item={x} series={series[x.case_id]} />)}
        </div>
      )}
    </div>
  );
}
