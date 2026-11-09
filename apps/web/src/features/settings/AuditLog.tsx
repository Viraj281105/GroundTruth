'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { createApiClient, type Schemas } from '../../lib/api-client';
import { apiErrorMessage, detailOf } from '../projects/model';
import styles from '../projects/projects.module.css';

type Event = Schemas['AuditEventView'];

/** Audit log, newest first, loaded a page at a time with the API's cursor. */
export function AuditLog({ orgSlug, initial, initialCursor }: { orgSlug: string; initial: Event[]; initialCursor: string | null }) {
  const [events, setEvents] = useState<Event[]>(initial);
  const [cursor, setCursor] = useState<string | null>(initialCursor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function more() {
    if (!cursor) return;
    setBusy(true);
    setError(null);
    try {
      const r = await createApiClient().GET('/orgs/{slug}/audit', { params: { path: { slug: orgSlug }, query: { cursor, limit: 50 } } });
      if (!r.data) return setError(apiErrorMessage(r.response.status, detailOf(r.error)));
      setEvents((e) => [...e, ...r.data!.events]);
      setCursor(r.data.next_cursor);
    } catch {
      setError(apiErrorMessage(0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.section}>
      {events.length === 0 ? (
        <p className={styles.muted}>No audit events yet.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
          <caption className={styles.srOnly}>Audit events</caption>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Action</th>
                <th scope="col">Resource</th>
                <th scope="col">Outcome</th>
                <th scope="col">Actor</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{e.occurred_at}</td>
                  <td>{e.action}</td>
                  <td>
                    {e.resource_type}
                    {e.resource_id ? ` ${e.resource_id}` : ''}
                  </td>
                  <td>{e.outcome}</td>
                  <td>{e.actor_user_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {cursor && (
        <div className={styles.actions}>
          <Button variant="secondary" onClick={more} loading={busy}>
            Load older events
          </Button>
        </div>
      )}
    </div>
  );
}
