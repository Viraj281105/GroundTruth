import React from 'react';
import { SetDataMode } from '../../../../../../components/shell/data-mode';
import { ProjectBadges } from '../../../../../../features/projects/ProjectBadges';
import { ProjectTabs } from '../../../../../../features/projects/ProjectTabs';
import { LifecycleProgress } from '../../../../../../components/panels/LifecycleProgress';
import { lifecycleSteps } from '../../../../../../components/panels/lifecycle.model';
import { claimSummary } from '../../../../../../features/assessments/model';
import { projectDataMode } from '../../../../../../features/projects/model';
import { fetched, loadProject } from '../../../../../../features/projects/server';
import { serverApi } from '../../../../../../lib/server-api';
import styles from '../../../../../../features/projects/projects.module.css';

export const dynamic = 'force-dynamic';

/** Project header, access badge, tabs, progress bar (statuses read from the API), and the data-mode banner trigger. Unknown or no-access projects 404. */
export default async function ProjectLayout({ children, params }: { children: React.ReactNode; params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const path = { params: { path: { project_id: project.id } } };
  const [inventory, assessment, claims, ledger, ingestions] = await Promise.all([
    fetched(() => serverApi().GET('/projects/{project_id}/evidence-inventory', path)),
    fetched(() => serverApi().GET('/projects/{project_id}/assessment', path)),
    fetched(() => serverApi().GET('/claims/structured/{project_id}', path)),
    fetched(() => serverApi().GET('/projects/{project_id}/ledger', path)),
    fetched(() => serverApi().GET('/projects/{project_id}/observations/ingestions', path)),
  ]);
  const steps = lifecycleSteps({ project, inventory: inventory.data, assessment: assessment.data, claims: claimSummary(claims.data), ledger: ledger.data, ingestions: ingestions.data });
  return (
    <>
      <SetDataMode mode={projectDataMode(project)} />
      <header className={styles.header}>
        <h1>{project.name}</h1>
        <p className={styles.meta}>
          {project.country} · {project.ecosystem} · {project.intervention} · treatment start {project.treatment_start_year}
        </p>
        <ProjectBadges project={project} />
      </header>
      <LifecycleProgress orgSlug={params.org} projectSlug={params.project} steps={steps} />
      <ProjectTabs base={`/app/${params.org}/projects/${params.project}`} level={project.access_level} />
      <div className={styles.stack}>{children}</div>
    </>
  );
}
