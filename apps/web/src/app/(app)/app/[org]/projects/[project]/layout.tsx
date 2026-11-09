import React from 'react';
import { SetDataMode } from '../../../../../../components/shell/data-mode';
import { ProjectBadges } from '../../../../../../features/projects/ProjectBadges';
import { ProjectTabs } from '../../../../../../features/projects/ProjectTabs';
import { projectDataMode } from '../../../../../../features/projects/model';
import { loadProject } from '../../../../../../features/projects/server';
import styles from '../../../../../../features/projects/projects.module.css';

export const dynamic = 'force-dynamic';

/** Project header, access badge, tabs and the data-mode banner trigger. Unknown or no-access projects 404. */
export default async function ProjectLayout({ children, params }: { children: React.ReactNode; params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
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
      <ProjectTabs base={`/app/${params.org}/projects/${params.project}`} level={project.access_level} />
      <div className={styles.stack}>{children}</div>
    </>
  );
}
