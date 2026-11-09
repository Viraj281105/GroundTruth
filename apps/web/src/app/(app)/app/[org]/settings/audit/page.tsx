import React from 'react';
import { ProblemPanel } from '../../../../../../features/projects/ProblemPanel';
import { fetched } from '../../../../../../features/projects/server';
import { AuditLog } from '../../../../../../features/settings/AuditLog';
import { requireSettingsAccess } from '../../../../../../features/settings/guard';
import { serverApi } from '../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Audit log' };

export default async function AuditPage({ params }: { params: { org: string } }) {
  await requireSettingsAccess(params.org);
  const r = await fetched(() => serverApi().GET('/orgs/{slug}/audit', { params: { path: { slug: params.org }, query: { limit: 50 } } }));
  return (
    <>
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: '0 0 var(--space-2)' }}>Audit log</h1>
      <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-5)' }}>Append-only record of security and data events for this organization, newest first.</p>
      {r.data ? <AuditLog orgSlug={params.org} initial={r.data.events} initialCursor={r.data.next_cursor} /> : <ProblemPanel title="Audit log" status={r.status} />}
    </>
  );
}
