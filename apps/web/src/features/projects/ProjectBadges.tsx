import React from 'react';
import { Chip } from '../../components/ds/Chip';
import { dataModeLabel, isLibraryCase, type ProjectView } from './model';
import styles from './projects.module.css';

/** Access level, owner and data-mode chips. Library cases get a plain label, never the simulated marker. */
export function ProjectBadges({ project }: { project: ProjectView }) {
  const library = isLibraryCase(project);
  return (
    <div className={styles.badges}>
      <Chip>Access: {project.access_level}</Chip>
      <Chip>Owner: {project.owner_name}</Chip>
      {library ? <Chip>{dataModeLabel(project)}</Chip> : project.data_mode === 'simulated' ? <Chip tone="sim" dot>{dataModeLabel(project)}</Chip> : <Chip>{dataModeLabel(project)}</Chip>}
    </div>
  );
}
