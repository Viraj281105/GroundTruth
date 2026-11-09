'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Card, Chip } from '../../components/ds';
import { cancelIngestion, fetchIngestions, requestIngestion } from './observations.client';
import {
  CHANGE_NOTE,
  INDICATOR_INFO,
  SEASON_HINT,
  SEASON_PRESETS,
  VEGETATION_NOTE,
  defaultForm,
  failureMessage,
  formatDateTime,
  formatElapsed,
  formatPct,
  formatValue,
  hasDetails,
  isActive,
  paramsSummary,
  shortSha,
  statusInfo,
  summariseResult,
  validateForm,
  valueColumns,
  yearStateInfo,
  type FormErrors,
  type IngestionList,
  type IngestionView,
  type ObservationForm,
} from './observations.model';
import styles from './ObservationIngestionPanel.module.css';

export const POLL_MS = 8000;

export interface ObservationIngestionPanelProps {
  projectId: string;
  initial: IngestionList;
  /** Owner-level access AND an org role that may edit. */
  canEdit: boolean;
  /** Plain-language reason shown instead of the form when canEdit is false. */
  blockedReason: string | null;
}

type Msg = { kind: 'ok' | 'error'; text: string; hint?: string | null } | null;

export function ObservationIngestionPanel({ projectId, initial, canEdit, blockedReason }: ObservationIngestionPanelProps) {
  const router = useRouter();
  const [list, setList] = useState<IngestionList>(initial);
  const [form, setForm] = useState<ObservationForm>(() => defaultForm(initial.limits));
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);

  const anyActive = list.ingestions.some((r) => isActive(r.status));
  const wasActive = useRef(anyActive);

  // Poll quietly while something is waiting or running. Errors are ignored; the next tick tries again.
  useEffect(() => {
    if (!anyActive) return;
    let stopped = false;
    const timer = setInterval(async () => {
      const r = await fetchIngestions(projectId);
      if (!stopped && r.ok) setList(r.data);
    }, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [anyActive, projectId]);

  // When the last active request reaches a final state, refresh the page once so the series and readiness update.
  useEffect(() => {
    if (wasActive.current && !anyActive) router.refresh();
    wasActive.current = anyActive;
  }, [anyActive, router]);

  const set = <K extends keyof ObservationForm>(k: K, v: ObservationForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  function pickSeason(id: ObservationForm['season']) {
    const p = SEASON_PRESETS.find((s) => s.id === id);
    setForm((f) => (p && id !== 'custom' ? { ...f, season: id, windowStart: p.start, windowEnd: p.end } : { ...f, season: id }));
  }

  function toggleIndicator(id: string, on: boolean) {
    setForm((f) => ({ ...f, indicators: on ? [...new Set([...f.indicators, id])] : f.indicators.filter((x) => x !== id) }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const v = validateForm(form, list.limits);
    setErrors(v.errors);
    if (!v.request) return setMsg({ kind: 'error', text: 'Please fix the highlighted fields first.' });
    setBusy(true);
    setMsg(null);
    const r = await requestIngestion(projectId, v.request);
    if (!r.ok) {
      setBusy(false);
      return setMsg({ kind: 'error', text: r.message, hint: r.hint });
    }
    const fresh = await fetchIngestions(projectId);
    if (fresh.ok) setList(fresh.data);
    else setList((l) => ({ ...l, active: true, ingestions: [r.data, ...l.ingestions.filter((x) => x.id !== r.data.id)] }));
    setBusy(false);
    setMsg({ kind: 'ok', text: 'Request received. It is waiting in the queue. A background worker will pick it up; no satellite data has been collected yet.' });
  }

  async function onCancel(r: IngestionView) {
    setCancelling(r.id);
    const res = await cancelIngestion(projectId, r.id);
    setCancelling(null);
    if (!res.ok) setMsg({ kind: 'error', text: res.message, hint: res.hint });
    else setMsg({ kind: 'ok', text: 'The request was cancelled.' });
    const fresh = await fetchIngestions(projectId);
    if (fresh.ok) setList(fresh.data);
  }

  const err = (f: keyof FormErrors) => (errors[f] ? <p className={styles.fieldError} role="alert">{errors[f]}</p> : null);
  const lim = list.limits;

  return (
    <Card className={styles.panel} aria-label="Request satellite data">
      <h2 className={styles.h2}>Request satellite data</h2>
      {list.enabled && <p className={styles.text}>{list.explanation}</p>}

      {!list.enabled ? (
        <p className={styles.notice} role="status" data-testid="ingestion-disabled">
          {list.explanation || 'Satellite requests are not available on this server right now.'}
        </p>
      ) : !canEdit ? (
        <p className={styles.notice} role="status" data-testid="ingestion-readonly">
          {blockedReason ?? 'You can see satellite requests here but you cannot make new ones.'}
        </p>
      ) : (
        <form className={styles.form} onSubmit={onSubmit} aria-label="New satellite data request" noValidate>
          <fieldset className={styles.fieldset}>
            <legend>Which years?</legend>
            <div className={styles.row}>
              <label className={styles.field}>
                First year
                <input inputMode="numeric" value={form.startYear} onChange={(e) => set('startYear', e.target.value)} aria-invalid={Boolean(errors.startYear)} />
                {err('startYear')}
              </label>
              <label className={styles.field}>
                Last year
                <input inputMode="numeric" value={form.endYear} onChange={(e) => set('endYear', e.target.value)} aria-invalid={Boolean(errors.endYear)} />
                {err('endYear')}
              </label>
            </div>
            {err('years')}
            <p className={styles.muted}>
              Satellite images are available from {lim.first_year}. You can ask for up to {lim.max_years} years at a time.
            </p>
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend>Which time of year?</legend>
            {SEASON_PRESETS.map((p) => (
              <label key={p.id} className={styles.choice}>
                <input type="radio" name="season" checked={form.season === p.id} onChange={() => pickSeason(p.id)} />
                <span>{p.label}</span>
              </label>
            ))}
            {form.season === 'custom' && (
              <div className={styles.row}>
                <label className={styles.field}>
                  Season starts (MM-DD)
                  <input value={form.windowStart} onChange={(e) => set('windowStart', e.target.value)} placeholder="06-01" aria-invalid={Boolean(errors.windowStart)} />
                  {err('windowStart')}
                </label>
                <label className={styles.field}>
                  Season ends (MM-DD)
                  <input value={form.windowEnd} onChange={(e) => set('windowEnd', e.target.value)} placeholder="06-30" aria-invalid={Boolean(errors.windowEnd)} />
                  {err('windowEnd')}
                </label>
              </div>
            )}
            <p className={styles.muted}>{SEASON_HINT}</p>
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend>What should be measured?</legend>
            {INDICATOR_INFO.filter((i) => lim.indicators.includes(i.id)).map((i) => (
              <label key={i.id} className={styles.choice}>
                <input
                  type="checkbox"
                  checked={i.always ? true : form.indicators.includes(i.id)}
                  disabled={i.always}
                  onChange={(e) => toggleIndicator(i.id, e.target.checked)}
                />
                <span>
                  {i.label}
                  <span className={styles.choiceHint}>{i.description}</span>
                </span>
              </label>
            ))}
            {err('indicators')}
          </fieldset>

          <details className={styles.advanced}>
            <summary>Advanced options</summary>
            <div className={styles.row} style={{ marginTop: 'var(--space-3)' }}>
              <label className={styles.field}>
                Cloud limit (%)
                <input inputMode="numeric" value={form.maxCloud} onChange={(e) => set('maxCloud', e.target.value)} aria-invalid={Boolean(errors.maxCloud)} />
                <span className={styles.choiceHint}>Skip scenes cloudier than this (0 to 80).</span>
                {err('maxCloud')}
              </label>
              <label className={styles.field}>
                Grid size (metres)
                <input inputMode="numeric" value={form.resolution} onChange={(e) => set('resolution', e.target.value)} aria-invalid={Boolean(errors.resolution)} />
                <span className={styles.choiceHint}>
                  {lim.min_resolution_m} to {lim.max_resolution_m}. Smaller is more detailed but slower.
                </span>
                {err('resolution')}
              </label>
              <label className={styles.field}>
                Scenes per year
                <input inputMode="numeric" value={form.scenesPerYear} onChange={(e) => set('scenesPerYear', e.target.value)} aria-invalid={Boolean(errors.scenesPerYear)} />
                <span className={styles.choiceHint}>Up to {lim.max_total_scenes} scenes in total across all years.</span>
                {err('scenesPerYear')}
              </label>
            </div>
          </details>

          <div className={styles.actions}>
            <Button type="submit" loading={busy} disabled={anyActive}>
              Request satellite data
            </Button>
            {anyActive && <span className={styles.muted}>A request is already waiting or running. Wait for it to finish before asking again.</span>}
          </div>
        </form>
      )}

      {msg?.kind === 'ok' && <p role="status" className={styles.text}>{msg.text}</p>}
      {msg?.kind === 'error' && (
        <p role="alert" className={styles.error}>
          {msg.text}
          {msg.hint ? <> {msg.hint}</> : null}
        </p>
      )}

      <h3 className={styles.h3}>Your requests</h3>
      {list.ingestions.length === 0 ? (
        <p className={styles.muted} data-testid="ingestion-empty">No satellite data has been requested for this project yet.</p>
      ) : (
        <ul className={styles.list} aria-label="Satellite data requests">
          {list.ingestions.map((r) => (
            <RequestItem key={r.id} r={r} canCancel={canEdit && r.status === 'queued'} cancelling={cancelling === r.id} onCancel={() => onCancel(r)} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function RequestItem({ r, canCancel, cancelling, onCancel }: { r: IngestionView; canCancel: boolean; cancelling: boolean; onCancel: () => void }) {
  const info = statusInfo(r.status);
  return (
    <li className={styles.item} data-ingestion-status={r.status}>
      <div className={styles.itemHead}>
        <Chip tone={info.tone}>{info.label}</Chip>
        <span className={styles.params}>{paramsSummary(r.params)}</span>
      </div>
      <p className={styles.text}>{info.explanation}</p>
      <p className={styles.times}>
        Requested {formatDateTime(r.created_at)}
        {isActive(r.status) ? ` (${formatElapsed(r.age_seconds)} ago)` : ''}
        {r.started_at ? ` · started ${formatDateTime(r.started_at)}` : ''}
        {r.finished_at ? ` · finished ${formatDateTime(r.finished_at)}` : ''}
      </p>
      {r.status_detail && r.status !== 'failed' && <p className={styles.text}>{r.status_detail}</p>}
      {r.waiting_hint && <p className={styles.notice} role="status">{r.waiting_hint}</p>}
      {r.status === 'failed' && <p className={styles.error} role="alert">{failureMessage(r)}</p>}
      {canCancel && (
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" loading={cancelling} onClick={onCancel}>
            Cancel request
          </Button>
        </div>
      )}
      {hasDetails(r.status) && <RequestDetails r={r} />}
    </li>
  );
}

function RequestDetails({ r }: { r: IngestionView }) {
  const res = r.result;
  const sentences = summariseResult(res);
  const years = res?.years ?? [];
  const cols = valueColumns(years, r.params.indicators ?? []);
  const cov = res?.coverage ?? null;
  const bundles = Object.entries(res?.stored_bundles ?? {});
  return (
    <details className={styles.details}>
      <summary>Details</summary>
      <div className={styles.detailsBody}>
        {!res && <p className={styles.muted}>This request has no result to show.</p>}
        {sentences.length > 0 && (
          <div>
            <h4 className={styles.h3}>In plain words</h4>
            {sentences.map((s) => (
              <p key={s} className={styles.text}>{s}</p>
            ))}
            <p className={styles.text}>{VEGETATION_NOTE}</p>
            <p className={styles.text}>{CHANGE_NOTE}</p>
          </div>
        )}
        {years.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className="sr-only">Result for each requested year</caption>
              <thead>
                <tr>
                  <th scope="col">Year</th>
                  <th scope="col">State</th>
                  <th scope="col">Scenes</th>
                  <th scope="col">Area covered</th>
                  <th scope="col">Tiles</th>
                  {cols.map((c) => (
                    <th key={c} scope="col">{c.toUpperCase()}</th>
                  ))}
                  <th scope="col">Acquired on</th>
                </tr>
              </thead>
              <tbody>
                {years.map((y) => {
                  const st = yearStateInfo(y.state);
                  return (
                    <tr key={y.year} data-year-state={y.state}>
                      <th scope="row">{y.year}</th>
                      <td><Chip tone={st.tone}>{st.label}</Chip></td>
                      <td>{y.n_scenes ?? '—'}</td>
                      <td>{formatPct(y.aoi_coverage_pct)}</td>
                      <td>{(y.contributing_tiles ?? []).join(', ') || '—'}</td>
                      {cols.map((c) => (
                        <td key={c}>{formatValue(y.values?.[c])}</td>
                      ))}
                      <td>{(y.acquisition_dates ?? []).join(', ') || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {cov && (
          <p className={styles.text}>
            Coverage check (an area counts as covered from {cov.threshold_pct}%): fully covered years: {cov.complete_years.join(', ') || 'none'}; partly covered years:{' '}
            {cov.partial_years.join(', ') || 'none'}; years without data: {cov.years_without_data.join(', ') || 'none'}.
          </p>
        )}
        {(res?.limitations ?? []).length > 0 && (
          <div>
            <h4 className={styles.h3}>Limits to keep in mind</h4>
            <ul className={styles.bullets}>
              {(res?.limitations ?? []).map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        )}
        {res && (
          <div>
            <h4 className={styles.h3}>Where this came from</h4>
            <dl className={styles.prov}>
              <dt>Catalog</dt>
              <dd>{res.catalog_url ?? '—'}</dd>
              <dt>Collection</dt>
              <dd>{res.collection ?? '—'}</dd>
              <dt>Satellite</dt>
              <dd>{res.platform ?? '—'}</dd>
              <dt>Code version</dt>
              <dd>{res.code_version ?? '—'}</dd>
              <dt>Method</dt>
              <dd>{res.method ?? '—'}</dd>
              <dt>Stored files</dt>
              <dd>
                {bundles.length === 0
                  ? '—'
                  : bundles.map(([k, b]) => (
                      <div key={k}>
                        {k.toUpperCase()}: <code>{b.file}</code> (fingerprint <code>{shortSha(b.sha256)}</code>)
                      </div>
                    ))}
              </dd>
              <dt>Ledger record</dt>
              <dd>{r.ledger_record_id ?? '—'}</dd>
            </dl>
          </div>
        )}
      </div>
    </details>
  );
}
