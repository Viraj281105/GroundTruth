import React from 'react';
import { ClimatePanel } from '../../../../../../../components/panels/ClimatePanel';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Climate' };

export default async function ClimatePage({ params }: { params: { project: string } }) {
  const project = await loadProject(params.project);
  const r = await fetched(() => serverApi().GET('/projects/{project_id}/climate', { params: { path: { project_id: project.id } } }));
  if (!r.data) return <ProblemPanel title="Climate" status={r.status} />;
  return <ClimatePanel data={r.data} observedWindow={undefined} />;
}
