import React from 'react';
import { EvidenceInventoryTable } from '../../../../../../../components/panels/EvidenceInventoryTable';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Evidence' };

export default async function EvidencePage({ params }: { params: { project: string } }) {
  const project = await loadProject(params.project);
  const r = await fetched(() => serverApi().GET('/projects/{project_id}/evidence-inventory', { params: { path: { project_id: project.id } } }));
  if (!r.data) return <ProblemPanel title="Evidence inventory" status={r.status} />;
  return <EvidenceInventoryTable data={r.data} level={project.access_level} />;
}
