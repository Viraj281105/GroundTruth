import React from 'react';
import { LedgerPanel } from '../../../../../../../features/projects/LedgerPanel';
import { ReportsView } from '../../../../../../../features/projects/ReportsView';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Reports' };

/** The project's case_id (needed for the legacy monitoring report routes) is on the verification payload. */
export default async function ReportsPage({ params }: { params: { project: string } }) {
  const project = await loadProject(params.project);
  const v = await fetched(() => serverApi().GET('/projects/{project_id}/verification', { params: { path: { project_id: project.id } } }));
  if (!v.data && v.status !== 403) return <ProblemPanel title="Reports" status={v.status} />;
  return (
    <>
      <ReportsView projectId={project.id} projectSlug={project.slug} level={project.access_level} caseId={v.data?.case_id ?? null} />
      <LedgerPanel projectId={project.id} />
    </>
  );
}
