import React from 'react';
import { GroqIntelligenceWorkspace } from '../../../../../components/panels/GroqIntelligenceWorkspace';
import { toServiceStatus, type ProjectOption, type ServiceStatus } from '../../../../../components/panels/intelligenceModel';
import { ProblemPanel } from '../../../../../features/projects/ProblemPanel';
import { fetched } from '../../../../../features/projects/server';
import { serverApi } from '../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Environmental Intelligence — GroundTruth 2.0' };

export default async function IntelligencePage({ params }: { params: { org: string } }) {
  const [list, status] = await Promise.all([
    fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } })),
    fetched(() => serverApi().GET('/intelligence/status')),
  ]);
  // The project list is the context for every question; without it nothing can be asked.
  if (!list.data) return <ProblemPanel title="Intelligence" status={list.status} needs="The organization's project list. No sample answer is shown." />;

  const projects: ProjectOption[] = list.data.map((p) => ({ id: p.id, name: p.name, simulated: p.data_mode === 'simulated' }));
  const service: ServiceStatus = status.data
    ? toServiceStatus(status.data)
    : { state: 'unavailable', reason: status.status === 0 ? 'The intelligence service could not be reached.' : `The status check failed (HTTP ${status.status}).` };

  return <GroqIntelligenceWorkspace orgSlug={params.org} projects={projects} service={service} />;
}
