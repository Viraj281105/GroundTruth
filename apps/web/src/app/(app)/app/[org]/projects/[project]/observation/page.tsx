import React from 'react';
import { IndexSeriesPanel } from '../../../../../../../components/panels/IndexSeriesPanel';
import type { ObservationsView } from '../../../../../../../components/panels/types';
import { ObservationIngestionPanel } from '../../../../../../../features/projects/ObservationIngestionPanel';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { canEditProject, editBlockedReason } from '../../../../../../../features/projects/model';
import { fetched, loadOrg, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Earth observation' };

const INDICATORS = ['ndvi', 'evi', 'ndmi', 'nbr'] as const;

/** The API serves one indicator per call, so all four are fetched; a failed one is simply absent (shown unavailable). */
export default async function ObservationPage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const org = await loadOrg(params.org);
  const role = org?.role ?? null;
  const ingestions = await fetched(() => serverApi().GET('/projects/{project_id}/observations/ingestions', { params: { path: { project_id: project.id } } }));
  const results = await Promise.all(
    INDICATORS.map((indicator) =>
      fetched(() => serverApi().GET('/projects/{project_id}/observations', { params: { path: { project_id: project.id }, query: { indicator } } })),
    ),
  );
  const series = results.map((r) => r.data).filter((d): d is ObservationsView => d !== null);
  return (
    <>
      {ingestions.data ? (
        <ObservationIngestionPanel
          projectId={project.id}
          initial={ingestions.data}
          canEdit={canEditProject(project.access_level, role)}
          blockedReason={editBlockedReason(project.access_level, role)}
        />
      ) : (
        <ProblemPanel title="Satellite data requests" status={ingestions.status} />
      )}
      {series.length === 0 ? <ProblemPanel title="Earth observation" status={results[0]?.status ?? 0} /> : <IndexSeriesPanel series={series} />}
    </>
  );
}
