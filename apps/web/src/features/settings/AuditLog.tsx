'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { createApiClient, type Schemas } from '../../lib/api-client';
import { apiErrorMessage, detailOf } from '../projects/model';
import styles from '../projects/projects.module.css';
import { actorLabel, collapseRuns, formatWhen, humanizeAction, humanizeOutcome, resourceLabel } from './audit-model';

// `actor_email` is additive on the API; this stays valid before and after the generated types include it.
type Event = Schemas['AuditEventView'] & { actor_email?: string | null };

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
              {collapseRuns(events).map(({ event: e, count }) => {
                const who = actorLabel(e);
                return (
                  <tr key={e.id}>
                    <td>
                      <time dateTime={e.occurred_at}>{formatWhen(e.occurred_at)}</time>
                    </td>
                    <td title={e.action}>
                      {humanizeAction(e.action)}
                      {count > 1 ? ` (×${count})` : ''}
                    </td>
                    <td title={e.resource_id ? `${e.resource_type} ${e.resource_id}` : e.resource_type}>{resourceLabel(e.resource_type, e.resource_id)}</td>
                    <td>{humanizeOutcome(e.outcome)}</td>
                    <td title={e.actor_user_id ?? undefined}>{who.text}</td>
                  </tr>
                );
              })}
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
