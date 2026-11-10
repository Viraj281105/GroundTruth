import React from 'react';
import { RunFlow } from '../../../../../../../features/run/RunFlow';
import { loadProject } from '../../../../../../../features/projects/server';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Run an analysis' };

/**
 * Start an analysis of this project and follow it to its result (#49).
 *
 * Access is what every page under /app/<org>/projects/<project> has: the org layout signs the
 * caller in and proves membership, `loadProject` answers 404 for a project the organization
 * cannot see, and the API refuses a run the caller's role may not start. The project's slug is
 * the id of the case its analysis runs on.
 */
export default async function RunPage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  return <RunFlow caseId={project.slug} basePath={`/app/${params.org}/projects/${params.project}`} />;
}
