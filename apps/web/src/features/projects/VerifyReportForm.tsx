'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { getApiBaseUrl } from '../../lib/api';
import { selectedSealingRecord, shortHash } from './ledger.model';
import styles from './projects.module.css';

type Result = { kind: 'idle' } | { kind: 'busy' } | { kind: 'ok'; text: string } | { kind: 'bad'; text: string };

/** Lets an auditor check a file they hold against the ledger record that sealed it. The server does the comparison. */
export function VerifyReportForm({ projectId, records }: { projectId: string; records: string[] }) {
  // The list grows while the page is open (a dossier download seals a new record and the page
  // reloads its data), so the selection is derived from the current list, not fixed at first render.
  const [chosen, setRecordId] = useState<string | null>(null);
  const recordId = selectedSealingRecord(chosen, records);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result>({ kind: 'idle' });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !recordId) return setResult({ kind: 'bad', text: 'Choose a file and a sealing record first.' });
    setResult({ kind: 'busy' });
    const body = new FormData();
    body.set('record_id', recordId);
    body.set('file', file);
    try {
      const res = await fetch(`${getApiBaseUrl()}/projects/${encodeURIComponent(projectId)}/ledger/verify-report`, { method: 'POST', body, credentials: 'include' });
      if (!res.ok) return setResult({ kind: 'bad', text: `The check could not be run (HTTP ${res.status}).` });
      const j = (await res.json()) as { verified: boolean; message: string };
      setResult(j.verified ? { kind: 'ok', text: j.message } : { kind: 'bad', text: j.message });
    } catch {
      setResult({ kind: 'bad', text: 'The GroundTruth API could not be reached.' });
    }
  }

  return (
    <form onSubmit={submit} className={styles.section} aria-label="Verify a downloaded report">
      <h3 style={{ margin: 0 }}>Check a downloaded report</h3>
      <p className={styles.muted}>Choose a dossier you were given and the ledger record that sealed it. GroundTruth confirms the file is byte-for-byte the sealed report.</p>
      <label>
        Sealing record{' '}
        <select value={recordId} onChange={(e) => setRecordId(e.target.value)}>
          {records.map((r) => (
            <option key={r} value={r}>{shortHash(r.replace('AUDIT-', ''), 8)}</option>
          ))}
        </select>
      </label>
      <label>
        Report file <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <div className={styles.actions}>
        <Button type="submit" variant="secondary" loading={result.kind === 'busy'}>Check file</Button>
      </div>
      {result.kind === 'ok' && <p role="status">{result.text}</p>}
      {result.kind === 'bad' && <p role="alert" className={styles.error}>{result.text}</p>}
    </form>
  );
}
