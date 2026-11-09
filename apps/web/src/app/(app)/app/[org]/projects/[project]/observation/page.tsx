import React from 'react';
import { IndexSeriesPanel } from '../../../../../../../components/panels/IndexSeriesPanel';
import type { ObservationsView } from '../../../../../../../components/panels/types';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Earth observation' };

const INDICATORS = ['ndvi', 'evi', 'ndmi', 'nbr'] as const;

/** The API serves one indicator per call, so all four are fetched; a failed one is simply absent (shown unavailable). */
export default async function ObservationPage({ params }: { params: { project: string } }) {
  const project = await loadProject(params.project);
  const results = await Promise.all(
    INDICATORS.map((indicator) =>
      fetched(() => serverApi().GET('/projects/{project_id}/observations', { params: { path: { project_id: project.id }, query: { indicator } } })),
    ),
  );
  const series = results.map((r) => r.data).filter((d): d is ObservationsView => d !== null);
  if (series.length === 0) return <ProblemPanel title="Earth observation" status={results[0]?.status ?? 0} />;
  return <IndexSeriesPanel series={series} />;
}
