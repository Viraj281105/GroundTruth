import React from 'react';
import { AssessmentSummary } from '../../../../../../../components/panels/AssessmentSummary';
import { ReadinessChecklist } from '../../../../../../../components/panels/ReadinessChecklist';
import { boundaryUrlFor, donorsUrlFor } from '../../../../../../../components/map/geo';
import ProjectMap from '../../../../../../../components/map/ProjectMap';
import { isLibraryCase } from '../../../../../../../features/projects/model';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadOrg, loadProject } from '../../../../../../../features/projects/server';
import styles from '../../../../../../../features/projects/projects.module.css';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Project overview' };

export default async function OverviewPage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const org = await loadOrg(params.org);
  const path = { project_id: project.id };
  const [assessment, readiness] = await Promise.all([
    fetched(() => serverApi().GET('/projects/{project_id}/assessment', { params: { path } })),
    fetched(() => serverApi().GET('/projects/{project_id}/readiness', { params: { path } })),
  ]);
  return (
    <>
      {assessment.data ? <AssessmentSummary data={assessment.data} persona={org?.type ?? null} /> : <ProblemPanel title="Assessment" status={assessment.status} />}
      <div className={styles.grid2}>
        {isLibraryCase(project) ? (
          <p className={styles.libraryNote}>Library case: this project has no uploaded boundary, so there is no map and no data to show.</p>
        ) : (
          <ProjectMap boundaryUrl={boundaryUrlFor(project.id)} donorsUrl={donorsUrlFor(project.id)} />
        )}
        {readiness.data ? <ReadinessChecklist data={readiness.data} /> : <ProblemPanel title="Readiness" status={readiness.status} />}
      </div>
    </>
  );
}
