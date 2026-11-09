import React from 'react';
import { ActivityFeed } from '../../../../../../../components/panels/ActivityFeed';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Project activity' };

/** The org-wide feed filtered to this project; the API already limits it to events the org may see. */
export default async function ActivityPage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const r = await fetched(() => serverApi().GET('/orgs/{slug}/activity', { params: { path: { slug: params.org }, query: { limit: 100 } } }));
  if (!r.data) return <ProblemPanel title="Activity" status={r.status} />;
  return (
    <>
      <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>Shows project events among the organization&apos;s most recent 100.</p>
      <ActivityFeed items={r.data.filter((i) => i.project_id === project.id)} />
    </>
  );
}
