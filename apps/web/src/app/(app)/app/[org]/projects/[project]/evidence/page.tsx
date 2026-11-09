import React from 'react';
import { EvidenceInventoryTable } from '../../../../../../../components/panels/EvidenceInventoryTable';
import { DocumentsPanel } from '../../../../../../../features/projects/DocumentsPanel';
import { EvidenceGuidance } from '../../../../../../../features/projects/EvidenceGuidance';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { editBlockedReason, canEditProject } from '../../../../../../../features/projects/model';
import { fetched, loadOrg, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Evidence' };

export default async function EvidencePage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const org = await loadOrg(params.org);
  const path = { params: { path: { project_id: project.id } } };
  const [inventory, docs] = await Promise.all([
    fetched(() => serverApi().GET('/projects/{project_id}/evidence-inventory', path)),
    fetched(() => serverApi().GET('/projects/{project_id}/documents', path)),
  ]);
  const role = org?.role ?? null;
  return (
    <>
      {inventory.data && <EvidenceGuidance inventory={inventory.data} />}
      {docs.data ? (
        <DocumentsPanel
          projectId={project.id}
          documents={docs.data.documents}
          maxBytes={docs.data.max_bytes}
          allowedExtensions={docs.data.allowed_extensions}
          canEdit={canEditProject(project.access_level, role)}
          blockedReason={editBlockedReason(project.access_level, role)}
        />
      ) : (
        <ProblemPanel title="Project documents" status={docs.status} />
      )}
      {inventory.data ? <EvidenceInventoryTable data={inventory.data} level={project.access_level} /> : <ProblemPanel title="Evidence inventory" status={inventory.status} />}
    </>
  );
}
